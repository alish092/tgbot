from langchain.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
import parse_documents

def main():
    print("📄 Парсим и фильтруем документы...")
    chunks = parse_documents.main()

    print("🔄 Генерируем эмбеддинги...")
    embedding_model = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    vectorstore = FAISS.from_documents(chunks, embedding_model)

    print("💾 Сохраняем векторную базу...")
    vectorstore.save_local("faiss_index")
    print("✅ База обновлена!")

if __name__ == "__main__":
    main()
