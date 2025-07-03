import streamlit as st
from openai import OpenAI
import json
import faiss
from datetime import date
import requests
from text_objects import *
from arkive_functions import *

index_name_path = "house_of_justice_all_2025-06-19/"
today = date.today()

FAISS_FILE = index_name_path + "embeddings_index.faiss"
DOCS_JSON = index_name_path + "docstore.json"
NAMES_JSON = index_name_path + "source_names.json"
URLS_JSON = index_name_path + "source_urls.json"

# === Load Metadata ===
with open(DOCS_JSON) as f:
    texts = json.load(f)
with open(NAMES_JSON) as f:
    names = json.load(f)
with open(URLS_JSON) as f:
    urls = json.load(f)

# === Load FAISS Index ===
index = faiss.read_index(FAISS_FILE)

# Initialize session state for authentication
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

# If not authenticated, show logo and password input
if not st.session_state.authenticated:
    col1, col2, col3 = st.columns([11, 20, 8])
    with col2:
        st.image("Logo_White_NoBG.png", width=250)

    st.write(
        "Arkive is a chatbot that answers your questions using messages from the Universal House of Justice. Please enter a password to use the app:"
    )


    # Password input
    entered_password = st.text_input("Password", type="password")
    actual_password = st.secrets["auth"]["entry_password"]

    if entered_password:
        if entered_password == actual_password:
            st.session_state.authenticated = True
            st.success("Access granted. You may now use the app.")
            st.rerun()
        else:
            st.info("Please enter the correct password to continue.", icon="🗝️")

# If authenticated, show the rest of your app
if st.session_state.authenticated:
    col1, col2, col3 = st.columns([11, 20, 8])
    with col2:
        st.image("Logo_White_NoBG.png", width=250)
    # API key from secrets
    openai_api_key = st.secrets["api_keys"]["openai"]
    client = openai.OpenAI(api_key=openai_api_key)
    default_model = "gpt-4.1"
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
    if user_query := st.chat_input("Ask anything from the guidance of the Universal House of Justice..."):

        # Store and display the current prompt.
        st.session_state.messages.append({"role": "user", "content": user_query})
        with st.chat_message("user"):
            st.markdown(user_query)

        context, distances = retrieve_top_k(user_query,index, texts, names, urls, k=4)

        # IF valid_query RETURNS FALSE THEN DO NOT RETURN CONTEXT (EXTRA COST)
        if valid_query(user_query, distances):
            prompt = build_prompt(user_query, context)
        else:
            prompt = user_query 
        # Generate a response using the OpenAI API.
        stream = client.chat.completions.create(
            model=default_model,
            messages=[
            {"role":"system"
            ,"content":system_prompt},
            {"role": "user",
            "content": prompt}],
                stream=True,
                stream_options={"include_usage": True}
            )
        # Stream the response to the chat using `st.write_stream`, then store it in 
        # session state.
        with st.chat_message("assistant"):
            # response = st.write_stream(stream)
            response, usage = stream_with_placeholder(stream)
        with st.chat_message("system"):
            usage_message = f"Token usage - Prompt: {usage.prompt_tokens} | Completion: {usage.completion_tokens} | Total: {usage.total_tokens} | "
            cost = usage_to_cost(usage, model=default_model)
            cost += 0.00001 #ADD AVG COST OF CALLING valid_query()
            cost_message = f"(Est. cost: ${cost:.5f})"
            st.markdown(usage_message+cost_message)
            # st.markdown(cost_message)
        st.session_state.messages.append({"role": "assistant", "content": response})
        st.session_state.messages.append({"role": "system", "content": usage_message+cost_message})
        # st.session_state.messages.append({"role": "system", "content": cost_message})


