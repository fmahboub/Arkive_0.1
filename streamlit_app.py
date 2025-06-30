import streamlit as st
from openai import OpenAI
from text_objects import *

# Show title and description.
st.title("💬 Arkive Chatbot")
st.write(
    "Arkive is a chatbot that answers your questions using selected messages from the Universal House of Justice, as published on Bahai.org."
    " To use this app, you need to enter a password:"
)

# Ask user for their OpenAI API key via `st.text_input`.
# Alternatively, you can store the API key in `./.streamlit/secrets.toml` and access it
# via `st.secrets`, see https://docs.streamlit.io/develop/concepts/connections/secrets-management
openai_api_key = st.secrets["api_keys"]["openai"]
entered_password = st.text_input("Password",type="password")
actual_password = st.secrets["auth"]["entry_password"]

if entered_password!= actual_password:
    st.info("Please enter the correct password to continue.", icon="🗝️")
else:

    # Create an OpenAI client.
    client = OpenAI(api_key=openai_api_key)

    # Create a session state variable to store the chat messages. This ensures that the
    # messages persist across reruns.
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Display the existing chat messages via `st.chat_message`.
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Create a chat input field to allow the user to enter a message. This will display
    # automatically at the bottom of the page.
    if prompt := st.chat_input("Ask anything about the Universal House of Justice's guidance..."):

        # Store and display the current prompt.
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Generate a response using the OpenAI API.
        stream = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
            {"role":"system"
            ,"content":system_prompt},
            {"role": "user",
            "content": prompt}],
                stream=True,
            )

        # Stream the response to the chat using `st.write_stream`, then store it in 
        # session state.
        with st.chat_message("assistant"):
            response = st.write_stream(stream)
        st.session_state.messages.append({"role": "assistant", "content": response})

