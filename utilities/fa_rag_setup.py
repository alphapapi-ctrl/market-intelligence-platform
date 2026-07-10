"""
utilities/fa_rag_setup.py
=========================
Builds (or rebuilds) the ChromaDB vector store from documents in docs/fa_reference/.
Run this whenever you add new reference documents.

Usage:
    python utilities/fa_rag_setup.py
"""

import os
import sys
import chromadb
from chromadb.utils import embedding_functions
from pypdf import PdfReader

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_DIR = os.path.join(BASE, 'docs', 'fa_reference')
CHROMA_DIR = os.path.join(BASE, 'data', 'fa_chromadb')

CHUNK_SIZE = 1500
CHUNK_OVERLAP = 200


def chunk_text(text, source_name, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """Split text into overlapping chunks with source metadata."""
    chunks = []
    paragraphs = text.split('\n\n')
    current_chunk = ''

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        if len(current_chunk) + len(para) + 2 > chunk_size and current_chunk:
            chunks.append(current_chunk.strip())
            # keep overlap from end of previous chunk
            words = current_chunk.split()
            overlap_words = []
            char_count = 0
            for w in reversed(words):
                char_count += len(w) + 1
                if char_count > overlap:
                    break
                overlap_words.insert(0, w)
            current_chunk = ' '.join(overlap_words) + '\n\n' + para
        else:
            current_chunk = current_chunk + '\n\n' + para if current_chunk else para

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return [{'text': c, 'source': source_name, 'chunk_idx': i}
            for i, c in enumerate(chunks)]


def build_vector_store():
    """Read all docs, chunk them, and store in ChromaDB."""
    os.makedirs(CHROMA_DIR, exist_ok=True)

    ef = embedding_functions.DefaultEmbeddingFunction()

    client = chromadb.PersistentClient(path=CHROMA_DIR)

    # delete existing collection if rebuilding
    try:
        client.delete_collection('fa_reference')
    except:
        pass

    collection = client.create_collection(
        name='fa_reference',
        embedding_function=ef,
        metadata={'description': 'Burry/Buffett fundamental analysis reference documents'}
    )

    all_chunks = []
    doc_files = []
    for root, _dirs, files in os.walk(DOCS_DIR):
        for f in files:
            if f.endswith('.txt') or f.endswith('.pdf'):
                doc_files.append(os.path.join(root, f))
    doc_files.sort()

    if not doc_files:
        print(f"No .txt or .pdf files found in {DOCS_DIR}")
        return

    for fpath in doc_files:
        rel_path = os.path.relpath(fpath, DOCS_DIR)

        if fpath.endswith('.pdf'):
            try:
                reader = PdfReader(fpath)
                text = '\n\n'.join(
                    page.extract_text() or '' for page in reader.pages
                )
            except Exception as e:
                print(f"  {rel_path}: SKIPPED — PDF read error: {e}")
                continue
        else:
            with open(fpath, 'r', encoding='utf-8') as f:
                text = f.read()

        if not text.strip():
            print(f"  {rel_path}: SKIPPED — no text extracted")
            continue

        source_name = os.path.splitext(rel_path)[0].replace('_', ' ').replace(os.sep, ' / ')
        chunks = chunk_text(text, source_name)
        all_chunks.extend(chunks)
        print(f"  {rel_path}: {len(chunks)} chunks")

    # add to ChromaDB in batches (chromadb has a batch limit)
    batch_size = 100
    for i in range(0, len(all_chunks), batch_size):
        batch = all_chunks[i:i + batch_size]
        collection.add(
            ids=[f"chunk_{i + j}" for j, _ in enumerate(batch)],
            documents=[c['text'] for c in batch],
            metadatas=[{'source': c['source'], 'chunk_idx': c['chunk_idx']} for c in batch],
        )

    print(f"\nDone — {len(all_chunks)} chunks from {len(doc_files)} documents stored in {CHROMA_DIR}")
    return collection


if __name__ == '__main__':
    print(f"Building FA vector store from: {DOCS_DIR}")
    print(f"Output: {CHROMA_DIR}\n")
    build_vector_store()
