# AI Virtual Try-On Backend

FastAPI backend for an AI virtual try-on MVP. Users upload a full-body image, select a product, and the API sends the user image plus garment image to Fal AI to generate a realistic try-on preview.

## Stack

- Python 3.11+
- FastAPI
- Pydantic
- MongoDB with Motor async driver
- Fal AI API
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
FAL_KEY=your_fal_api_key
MONGODB_URI=mongodb+srv://<username>:<password>@<cluster-url>/?retryWrites=true&w=majority&appName=VirtualTryOn
DATABASE_NAME=virtual_tryon_db
FAL_MODEL=fal-ai/gemini-25-flash-image/edit
ADMIN_USERNAME=admin
ADMIN_PASSWORD=change-this-password
JWT_SECRET_KEY=generate-a-long-random-secret-with-openssl-rand-hex-32
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=1440
JWT_ACCESS_COOKIE_NAME=admin_access_token
JWT_ACCESS_COOKIE_SECURE=false
JWT_ACCESS_COOKIE_SAMESITE=lax
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://localhost:3001,https://ai-closet-viewer.vercel.app
CLOUDINARY_CLOUD_NAME=your_cloudinary_cloud_name
CLOUDINARY_API_KEY=your_cloudinary_api_key
CLOUDINARY_API_SECRET=your_cloudinary_api_secret
CLOUDINARY_FOLDER=ai-fit-studio
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

Products are seeded automatically on startup into the `products` collection.

The admin dashboard user is seeded automatically from `ADMIN_USERNAME` and `ADMIN_PASSWORD` into the `admin_users` collection each time the backend starts.

### Admin overview

- `GET /api/admin/dashboard`

Requires an admin bearer token. Returns inventory totals, all-time and current-day try-on counts, a seven-day try-on series, the most-used product, recent products, per-product usage, and recent try-on activity for the dashboard overview.

### Uploads

- `POST /api/uploads/user-photo`

Accepts `jpg`, `jpeg`, `png`, and `webp` files up to 10MB. In production, configure Cloudinary so uploads are stored remotely and returned as public HTTPS URLs. Without Cloudinary, local development falls back to `uploads/user_photos`.

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

Generated results are stored in Cloudinary when configured. Local development falls back to `uploads/results`. History is stored in the `tryon_results` MongoDB collection.

Each try-on result now also stores `image_details`, including the Fal provider name, model ID, source output URL, content type, file size, optional width/height, and Fal's returned `seed` when available.

## Notes

- Keep `.env` private. Never expose `FAL_KEY` to the frontend.
- Configure `CORS_ALLOWED_ORIGINS` with a comma-separated list of frontend origins that should be allowed to call the API with credentials.
- Product image URLs should be publicly reachable or otherwise accessible to the backend.
- The Fal implementation uses the Python `fal_client.subscribe(...)` flow with the `fal-ai/gemini-25-flash-image/edit` style input shape: `image_urls` plus `prompt`.
