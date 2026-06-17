from transformers import pipeline

class ModelService:
    def __init__(self):
        self.model = None

    def load_model(self, model_name: str):
        # Using a simple text classification pipeline as an example
        print(f"Loading model: {model_name}...")
        self.model = pipeline("text-classification", model=model_name)
        print("Model loaded successfully.")

    def predict(self, text: str) -> list:
        if self.model is None:
            raise ValueError("Model is not loaded yet.")
        return self.model(text)
