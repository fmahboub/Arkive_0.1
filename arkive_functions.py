import openai
import streamlit as st
import numpy as np
import faiss
import time

openai.api_key = st.secrets["api_keys"]["openai"]

def embed_texts(texts, model="text-embedding-3-large", batch_size=100):
    embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        response = openai.embeddings.create(input=batch, model=model)
        batch_embeddings = [np.array(e.embedding, dtype=np.float32) for e in response.data]
        embeddings.extend(batch_embeddings)
    return embeddings

def format_context(chunk: str, document_name: str, url: str) -> str:
    return f"""Source: {document_name}\n\nURL: {url}\n\n{chunk}"""

def format_multiple_contexts(chunks: list[dict]) -> str:
    formatted_chunks = []
    for c in chunks:
        formatted_chunks.append(
            f"""---\nSource: {c['document_name']}\nURL: {c['url']}\n\n{c['chunk']}"""
        )
    return "\n\n".join(formatted_chunks)

def retrieve_top_k(user_query, index, texts, names, urls, k=5):
  if k == 0:
    return ''
  query_vector = embed_texts([user_query])[0].reshape(1, -1)
  # RETURN DOUBLE WHAT IS NEEDED
  distances, indices = index.search(query_vector, k*2)
  chunks = []
  for i in range(k*2):
      if len(chunks) >= k:
        break
      doc_name = names[indices[0][i]].replace('__',' - ').replace('_', ' ').strip('.json')
      text = texts[indices[0][i]]
      # REMOVE ANY CHUNK WITH LESS THAN 5 WORDS
      if len(text.split()) < 5:
        continue
      chunks.append({"chunk":texts[indices[0][i]], "document_name":doc_name, "url":urls[indices[0][i]]})
  chunks = format_multiple_contexts(chunks)
  return chunks, distances

def build_prompt(user_query, context):
  # Build prompt
  prompt = f"Use the following context to answer the question:\n{context}\
  \n\nQuestion: {user_query}\nAnswer:"
  return prompt

def stream_with_placeholder(stream):
  placeholder = st.empty()  # Reserve a spot for updating text
  response_text = ""
  usage = None

  for chunk in stream:
      if chunk.usage:
          usage = chunk.usage
      else:
          delta = chunk.choices[0].delta
          content = getattr(delta, "content", "")
          if content:
              response_text += content
              placeholder.markdown(response_text)  # Update the whole accumulated text

              # Optional: small delay to make streaming effect visible
              time.sleep(0.01)

  return response_text, usage

def usage_to_cost(usage, model, use_cached_input=False):
    pricing_table = {
    "gpt-4.1": {
        "prompt": 2.00 / 1_000_000,
        "cached_prompt": 0.50 / 1_000_000,
        "completion": 8.00 / 1_000_000,
    },
    "gpt-4.1-mini": {
        "prompt": 0.40 / 1_000_000,
        "cached_prompt": 0.10 / 1_000_000,
        "completion": 1.60 / 1_000_000,
    },
    "gpt-4.1-nano": {
        "prompt": 0.10 / 1_000_000,
        "cached_prompt": 0.025 / 1_000_000,
        "completion": 0.40 / 1_000_000,
    },
}
    
    price = pricing_table.get(model)
    if price is None:
        raise ValueError(f"Unknown model pricing for {model}")

    prompt_price = price["cached_prompt"] if use_cached_input else price["prompt"]
    
    prompt_cost = usage.prompt_tokens * prompt_price
    completion_cost = usage.completion_tokens * price["completion"]
    
    return prompt_cost + completion_cost

def valid_query(prompt, distances,):
    client = openai.OpenAI(api_key=openai.api_key)

    system_message = "Is it remotely possible that the following text can be answered by the writings of the Universal House of Justice? Lean yes if unsure and answer only 'yes' or 'no'"
    full_prompt = f'"{prompt}"'

    response = client.chat.completions.create(
        model="gpt-4.1-nano",
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": full_prompt}
        ]
    )

    answer = response.choices[0].message.content.strip().lower()

    if answer == 'yes' or distances[0][0] < 1.4:
        return True
    else:
        return False