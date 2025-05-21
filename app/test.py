import os
import re
from .models.config import config
from .models.db import Transcription, Channels, Video
from langchain_ollama import OllamaLLM, OllamaEmbeddings
from langchain_core.documents import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_postgres import PGVector
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from langchain.prompts import ChatPromptTemplate


ollama_url = "https://ollama.disp.lease"
connection = "postgresql+psycopg://root:secret@localhost:5432/postgres"
collection_name = "my_docs"

db2 = create_engine(connection)
Session = sessionmaker(bind=db2)
session = Session()
# Initialize the LLM
current_dir = os.path.dirname(os.path.abspath(__file__))
model = OllamaLLM(model="gemma3:12b", base_url=ollama_url)
embeddings = OllamaEmbeddings(model="nomic-embed-text", base_url=ollama_url)

db = PGVector(
    embeddings=embeddings,
    collection_name=collection_name,
    connection=connection,
    use_jsonb=True,
)
template = '''
Based on the following context, answer the question. The context is a transcribed conversation from a video and everything in the context might not be relevant to the question.

Context: {context}

Question: {question}
'''

summary_template = '''
Based on the following context, generate a concise, factual summary (or set of summaries) of the conversation.

The conversation is a transcription from a Twitch live stream where the user (named {broadcaster_name}) speaks to an audience or another person.

Instructions:
- Only mention the broadcaster’s name ({broadcaster_name}) if it’s absolutely necessary for clarity or contrast.
- Do not include opinions, emotional tones, or subjective interpretations (e.g., avoid words like “humorously,” “happily,” “frustrated,” “exciting”).
- Do not describe general chatting or vague engagement with the audience.
- Focus on concrete actions, statements, or stories that are specific, informative, or unusual.
- Group related topics into short summaries (1–2 sentences max), and only include multiple summaries if distinct topics are discussed.
- Exclude filler, greetings, and routine interactions unless essential to context.
- Exclude gifts, donations, subscriptions and other non-conversation related content.
- Do not hallucinate or make things up.
- Only give summary in bullet points, do not include any other text

The user is named: {broadcaster_name}
About the user: {broadcaster_description}

Context: {context}
'''

def metadata_func(record: dict, metadata: dict) -> dict:
    metadata["start"] = record.get("start")
    metadata["end"] = record.get("end")
    metadata["segment_ids"] = record.get("segment_ids")
    return metadata


def clean_summary_lines(summary_text, username=None):
    """
    Cleans summary bullet points by:
    - Removing leading subject phrases ('The user', 'The streamer', or a username)
    - Normalizing bullet points
    - Capitalizing the first word
    - Stripping extra whitespace

    Parameters:
        summary_text (str): Full text of bullet-pointed summaries.
        username (str): Optional username to remove.

    Returns:
        str: Cleaned and formatted summaries.
    """
    lines = summary_text.strip().splitlines()
    cleaned_lines = []

    # Build pattern for matching leading subject phrases
    subjects = ["The streamer", "The user"]
    if username:
        subjects.append(re.escape(username))
    subject_pattern = r"^[-*•]?\s*(" + "|".join(subjects) + r")\s+"

    for line in lines:
        # Remove leading subject if present
        cleaned = re.sub(subject_pattern, "", line.strip(), flags=re.IGNORECASE)
        # Remove any bullet/whitespace and re-add standard bullet
        cleaned = re.sub(r"^[-*•]?\s*", "", cleaned)
        # Capitalize first letter
        if cleaned:
            cleaned = cleaned[0].upper() + cleaned[1:]
            cleaned_lines.append(f"* {cleaned}")

    return "\n".join(cleaned_lines)

def make_chunks(transcription: Transcription, chunk_size: int = 600):

    segments = transcription.segments
    segments.sort(key=lambda x: x.start)

    chunks = []
    current_chunk = {
        "start": segments[0].start,
        "end": segments[0].end,
        "segment_ids": [],
        "text": ""
    }
    chunk_end_time = current_chunk["start"] + chunk_size

    for segment in segments:
        if segment.start < chunk_end_time:
            current_chunk["segment_ids"].append(segment.id)
            current_chunk["text"] += segment.text.strip() + " "
            current_chunk["end"] = max(current_chunk["end"], segment.end)
        else:
            # Save the completed chunk
            current_chunk["text"] = current_chunk["text"].strip()
            chunks.append(current_chunk)

            # Start a new chunk
            current_chunk = {
                "start": segment.start,
                "end": segment.end,
                "segment_ids": [segment.id],
                "text": segment.text.strip() + " "
            }
            chunk_end_time = segment.start + chunk_size

    # Append the last chunk
    if current_chunk["segment_ids"]:
        current_chunk["text"] = current_chunk["text"].strip()
        chunks.append(current_chunk)
    return chunks

def process_transcriptions(channel_id: int):
    channel =  session.execute(select(Channels).filter_by(id=channel_id)).scalars().one()
    transcriptions: list[Transcription] = []
    for video in channel.videos:
        if video.active:
            transcriptions += video.transcriptions
    for transcription in transcriptions:
        print("Processing transcription", transcription.id)
        chunks = make_chunks(transcription)
        documents = [Document(page_content=chunk["text"], metadata=metadata_func(chunk, {})) for chunk in chunks]
        
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=25)
        
        docs = text_splitter.split_documents(documents)
        db.add_documents(docs, ids=[str(transcription.id) + "_" + str(i) for i in range(len(chunks))])

def main():
    # query = "What is the kind of food preferences does the person have?"
    query = "does this person have a dog?"
    
    retriever = db.as_retriever(
        search_type="similarity_score_threshold",
        search_kwargs={
            "k": 3,
            "score_threshold": 0.4
        }
    )
    retrieved_docs = retriever.invoke(query)

    prompt_template = ChatPromptTemplate.from_template(template)
    prompt = prompt_template.invoke({"context": "\n\n".join([doc.page_content for doc in retrieved_docs]), "question": query})
    print(prompt.to_messages())
    print("\n\n")
    
    result = model.invoke(prompt)
    print(result)
    
    # for i, segment in enumerate(data["segments"]):

def channel_summary(channel_id: int):
    channel = session.execute(select(Channels).filter_by(id=channel_id)).scalars().one()
    transcriptions: list[Transcription] = []
    for video in channel.videos:
        if video.active:
            transcriptions += video.transcriptions
    for transcription in transcriptions:
        print("Processing transcription", transcription.id)
        summary(transcription)

def summary(transcription: Transcription):
    chunks = make_chunks(transcription)
    documents: Document = [] 
    for chunk in chunks:
        context = chunk["text"]
        prompt_template = ChatPromptTemplate.from_template(summary_template)
        prompt = prompt_template.invoke({"context": context, "broadcaster_name": "fanfan", "broadcaster_description": "female twitch streamer known for talking with her chat and playing video games"})
        result = clean_summary_lines(model.invoke(prompt), "fanfan")
        documents.append(Document(page_content=result, metadata=metadata_func(chunk, {})))
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=25)
    
    docs = text_splitter.split_documents(documents)
    db.add_documents(docs, ids=[str(transcription.id) + "_" + str(i) + "_summary" for i in range(len(chunks))])
if __name__ == "__main__":
    # main()
    # summary()
    channel_summary(7)
    channel_summary(2)
    # process_transcriptions(7)