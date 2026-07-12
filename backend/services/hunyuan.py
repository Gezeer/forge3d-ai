from gradio_client import Client, handle_file

class HunyuanService:

    def __init__(self):
        self.client = None

    def connect(self):
        if self.client is None:
            self.client = Client("http://127.0.0.1:8080")
        return self.client

    def ping(self):
        self.connect()
        return True


    def generate(self, image_path):
        client = self.connect()
        return client.predict(
            None, handle_file(image_path),
            None, None, None, None,
            30, 5.0, 1234, 256,
            True, 8000, True,
            api_name="/generation_all"
        )
