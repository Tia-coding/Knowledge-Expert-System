from sentence_transformers import SentenceTransformer


def main() -> None:
    model_name = "sentence-transformers/all-MiniLM-L6-v2"
    print(f"Caching embedding model: {model_name}")
    SentenceTransformer(model_name)
    print("Embedding model cached successfully.")
    print("For full offline mode, also make sure Ollama models are installed:")
    print("  ollama list")
    print("Required local LLM options:")
    print("  phi3:mini")
    print("  tinyllama")


if __name__ == "__main__":
    main()