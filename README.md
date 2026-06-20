# AI Virtual Try-On Backend

FastAPI backend for an AI virtual try-on MVP. Users upload a full-body image, select a product, and the API sends the user image plus garment image to OpenAI to generate a realistic try-on preview.

## Stack

- Python 3.11+
- FastAPI
- Pydantic
- MongoDB with Motor async driver
- OpenAI API
- python-dotenv

## Setup

1. Create a virtual environment:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Create your environment file:

```bash
cp .env.example .env
```

4. Fill in `.env`:

```env
OPENAI_API_KEY=your_openai_key
MONGODB_URI=mongodb+srv://<username>:<password>@<cluster-url>/?retryWrites=true&w=majority&appName=VirtualTryOn
DATABASE_NAME=virtual_tryon_db
OPENAI_MODEL=gpt-5.5
```

5. Create a MongoDB Atlas cluster and set `MONGODB_URI` to your Atlas connection string.

   In Atlas, make sure you:

   - Create a database user and password.
   - Add your current IP address in **Network Access**.
   - Replace `<username>`, `<password>`, and `<cluster-url>` in `.env`.

6. Run the API:

```bash
uvicorn app.main:app --reload
```

The API runs at `http://localhost:8000`.

## API Docs

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- Health check: `GET /health`

## Endpoints

### Products

- `GET /api/products`
- `GET /api/products/{product_id}`
- `POST /api/products`
- `PUT /api/products/{product_id}`
- `DELETE /api/products/{product_id}`

Products are seeded automatically on startup into the `products` collection if they do not already exist.

### Uploads

- `POST /api/uploads/user-photo`

Accepts `jpg`, `jpeg`, `png`, and `webp` files up to 10MB. Files are saved to `uploads/user_photos` and returned as local public URLs.

### Try-On

- `POST /api/tryon/generate`
- `GET /api/tryon/history`
- `GET /api/tryon/history/{id}`

Example request:

```json
{
  "user_image_url": "/uploads/user_photos/example.png",
  "product_id": "linen-oxford-shirt",
  "prompt_optional": "Keep the outfit modest and realistic."
}
```

Generated results are saved to `uploads/results`, and history is stored in the `tryon_results` MongoDB collection.

## Notes

- Keep `.env` private. Never expose `OPENAI_API_KEY` to the frontend.
- CORS is configured to accept requests from any frontend origin during MVP development.
- Product image URLs should be publicly reachable or otherwise accessible to the backend.
- The OpenAI implementation uses the Responses API with the `image_generation` tool and sends both the user image and garment image as image inputs.
