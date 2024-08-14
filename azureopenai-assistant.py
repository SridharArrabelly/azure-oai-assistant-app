import os
import streamlit as st
from openai import  AssistantEventHandler
from typing_extensions import override
from openai.types.beta.threads import Text, TextDelta
from openai import AzureOpenAI
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class EventHandler(AssistantEventHandler):
    """
    Event handler for the assistant stream
    """

    @override
    def on_event(self, event):
        # Retrieve events that are denoted with 'requires_action'
        # since these will have our tool_calls
        if event.event == 'thread.run.requires_action':
            run_id = event.data.id  # Retrieve the run ID from the event data
            self.handle_requires_action(event.data, run_id)

    @override
    def on_text_created(self, text: Text) -> None:
        """
        Handler for when a text is created
        """
        # This try-except block will update the earlier expander for code to complete.
        # Note the indexing. We are updating the x-1 textbox where x is the current textbox.
        # Note how `on_tool_call_done` creates a new textbook (which is the x_th textbox, so we want to access the x-1_th)
        # This is to address an edge case where code is executed, but there is no output textbox (e.g. a graph is created)
        try:
            st.session_state[f"code_expander_{len(st.session_state.text_boxes) - 1}"].update(state="complete",
                                                                                             expanded=False)
        except KeyError:
            pass

        # Create a new text box
        st.session_state.text_boxes.append(st.empty())
        # Display the text in the newly created text box
        st.session_state.text_boxes[-1].info("".join(st.session_state["assistant_text"][-1]))

    @override
    def on_text_delta(self, delta: TextDelta, snapshot: Text):
        """
        Handler for when a text delta is created
        """
        # Clear the latest text box
        st.session_state.text_boxes[-1].empty()
        # If there is text written, add it to latest element in the assistant text list
        if delta.value:
            st.session_state.assistant_text[-1] += delta.value
            #st.session_state.chat_history.append(("assistant", delta.value))
        # Re-display the full text in the latest text box
        st.session_state.text_boxes[-1].info("".join(st.session_state["assistant_text"][-1]))

    def on_text_done(self, text: Text):
        """
        Handler for when text is done
        """
        # Create new text box and element in the assistant text list
        st.session_state.text_boxes.append(st.empty())
        st.session_state.assistant_text.append("")
        st.session_state.chat_history.append(("assistant", text.value))

    def submit_tool_outputs(self, tool_outputs):
        # Use the submit_tool_outputs_stream helper
        with client.beta.threads.runs.submit_tool_outputs_stream(
                thread_id=self.current_run.thread_id,
                run_id=self.current_run.id,
                tool_outputs=tool_outputs,
                event_handler=EventHandler(),
        ) as stream:
            for text in stream.text_deltas:
                print(text, end="", flush=True)
            print()

# Initialize the OpenAI client

client = AzureOpenAI(
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_key= os.getenv("AZURE_OPENAI_API_KEY"),
    api_version="2024-05-01-preview"
)
# assistant = client.beta.assistants.create(
#     model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"), # replace with model deployment name.
#     instructions="You are an AI Assistant tasked with analyzing support incident data, it's important to note that each row in the provided file represents a single ticket, with the first row detailing the column names. Please ensure you review the data thoroughly and base your analysis on the information presented, avoiding any assumptions or fabricated responses.",
#     tools=[{"type":"code_interpreter"}],
#     tool_resources={"code_interpreter":{"file_ids":[os.getenv("FILE_IDS")]}},
#     temperature=1,
#     top_p=1
# )

st.title("💬 Mantrac incident analysis")
text_box = st.empty()


# Initialize chat history in session state if not already done
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []

if "assistant_text" not in st.session_state:
    st.session_state.assistant_text = [""]

if "thread_id" not in st.session_state:
    thread = client.beta.threads.create()
    st.session_state.thread_id = thread.id

if "text_boxes" not in st.session_state:
    st.session_state.text_boxes = []

def display_chat_history():
    for role, content in st.session_state.chat_history:
        if role == "user":
            st.chat_message("User").write(content)
        else:
            st.chat_message("Assistant").write(content)

display_chat_history()

if prompt := st.chat_input("Enter your question"):
    st.session_state.chat_history.append(("user", prompt))

    client.beta.threads.messages.create(
        thread_id=st.session_state.thread_id,
        role="user",
        content=prompt
    )

    st.session_state.text_boxes.append(st.empty())
    st.session_state.text_boxes[-1].success(f" {prompt}")

    with client.beta.threads.runs.stream(thread_id=st.session_state.thread_id,
                                         assistant_id=os.getenv("ASSISTANT_ID"),
                                         event_handler=EventHandler(),
                                         temperature=0) as stream:
        stream.until_done()

