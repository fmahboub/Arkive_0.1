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
  return chunks

def build_prompt(user_query, context):
  # Build prompt
  prompt = f"Use the following context to answer the question:\n{context}\
  \n\nQuestion: {user_query}\nAnswer:"
  return prompt