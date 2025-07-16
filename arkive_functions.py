import openai
import streamlit as st
import numpy as np
import faiss
import time
import json
from datetime import date
from text_objects import *

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

def retrieve_top_k(user_query, index, texts, names, urls, time_range, temporal_bias, query_complexity, k=4):
  
  # RETURN BLANK IF K=0
  if k == 0:
    return ''

  # UPDATE k DEPENDING ON DETECTED COMPLEXITY
  if query_complexity == 'moderate' or query_complexity == 'deep':
    k *= 2

  query_vector = embed_texts([user_query])[0].reshape(1, -1)
  time_range = time_range['time_range']
  # RETURN 10x WHAT IS NEEDED (IN CASE OF TIME PERIOD CONSTRAINTS, SMALL CHUNKS OR TEMPORAL BIAS FILTERING)
  distances, indices = index.search(query_vector, k*10)
  filtered_distances = []
  chunks = []
  for i in range(k*10):
    # ONLY STOP AT k IF THERE'S NO TEMPORAL BIAS
    if len(chunks) >= k and temporal_bias == 'neutral':
      break
    doc_name = names[indices[0][i]].replace('__',' - ').replace('_', ' ').replace('– ',' ').strip('.json')
    # EXTRACT THE DOC YEAR TRYING TWO DIFFERENT METHODS (GREGORIAN vs. B.E.)
    try:
      potential_years = [word.replace(')','').replace('(','') for word in doc_name.split()]
      potential_years = [word for word in potential_years if len(word) == 4 and word.isnumeric()]
      doc_year = int(potential_years[0])
    except: #USE 3 DIGIT NUMBERS TO CONVERT BAHAI ERA TO GREGORIAN
      potential_years = [word.replace(')','').replace('(','') for word in doc_name.split()]
      potential_years = [word for word in potential_years if len(word) == 3 and word.isnumeric()]
      try:
        doc_year = int(potential_years[0]) + 1843
      except: # TEMP
        doc_year = 1980
    text = texts[indices[0][i]]
    # IGNORE ANY CHUNK WITH LESS THAN 5 WORDS
    if len(text.split()) < 5:
      continue
    # CHECK IF THERE'S A TIME RANGE
    if time_range != None:
      # IGNORE ANY CHUNKS OUTSIDE OF THE TIME RANGE (BUFFER - 2 YEARS FOR LOOK AHEADS)
      if doc_year < (time_range['start_year']-2) or doc_year > time_range['end_year']:
        continue

    chunks.append({
            "chunk": text,
            "document_name": doc_name,
            "url": urls[indices[0][i]],
            "year": doc_year,
        })

    # Apply temporal rerank
    if temporal_bias == 'prefer_recent':
        chunks = sorted(chunks, key=lambda x: x['year'], reverse=True)
    elif temporal_bias == 'prefer_early':
        chunks = sorted(chunks, key=lambda x: x['year'])
    # else: do nothing — already semantically sorted

    top_chunks = chunks[:k]
    filtered_distances.append(distances[0][i])

  # COMBINE ALL CHUNKS AND META-DATA INTO ONE STRING
  top_chunks = format_multiple_contexts(top_chunks)

  return top_chunks, distances

def build_prompt(user_query, context, is_valid):
  if not is_valid:
     context = 'Nothing Found'
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

def valid_query(prompt, distances):
    client = openai.OpenAI(api_key=openai.api_key)

    system_message = "Is it remotely possible that the following text can be answered by the writings of the Universal House of Justice? Lean yes if unsure and answer only 'yes' or 'no'"
    full_prompt = f'"{prompt}"'

    response = client.chat.completions.create(
        model="gpt-4.1-nano",
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": full_prompt}
        ],
        temperature = 0
    )

    answer = response.choices[0].message.content.strip().lower()
    if answer == 'yes' or distances[0][0] < 1.6:
        return True, response.usage
    else:
        return False, response.usage

def get_time_range(user_query):
  # Call OpenAI using the new API structure
  client = openai.OpenAI(api_key=openai.api_key)

  response = client.chat.completions.create(
      model="gpt-4.1-mini",
      messages=[
          {"role":"system"
          ,"content":get_time_range_system_prompt},
          {"role": "user",
          "content": user_query}],
          temperature=0
          )
  try:
    time_range = json.loads(response.choices[0].message.content)
    # CHECK IF RANGE IS EFFECTIVELY NONE
    if time_range['time_range']['start_year'] <= 1963 and time_range['time_range']['end_year'] >= int(today.split('-')[0]):
      return {"time_range": None}, response.usage
    else:
      return time_range, response.usage
  except:
    # print("Error: Couldn't reformat to JSON")
    # print(response.choices[0].message.content)
    return {"time_range": None}, response.usage

def get_temporal_bias(user_query):
  client = openai.OpenAI(api_key=openai.api_key)

  response = client.chat.completions.create(
      model="gpt-4.1-mini",
      messages=[
          {"role":"system"
          ,"content":temporal_bias_system_prompt},
          {"role": "user",
          "content": user_query}],
          temperature=0
          )
  usage = response.usage
  response_string = response.choices[0].message.content.strip().lower()
  if response_string not in ['prefer_recent', 'prefer_early', 'neutral']:
    response_string = 'neutral'
  return response_string, usage

def determine_complexity(user_query):
  # Call OpenAI using the new API structure

  client = openai.OpenAI(api_key=openai.api_key)

  response = client.chat.completions.create(
      model="gpt-4.1-mini",
      messages=[
          {"role":"system"
          ,"content":determine_complexity_system_prompt},
          {"role": "user",
          "content": user_query}],
          temperature=0
          )
  usage = response.usage
  response_string = response.choices[0].message.content.strip().lower()
  if response_string not in ['shallow', 'moderate', 'deep']:
    response_string = 'moderate'
  return response_string, usage