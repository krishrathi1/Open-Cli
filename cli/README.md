# Rathi CLI (Distributed Node Launcher)

This is the **client-side Node.js CLI** wrapper that connects to your hosted Python Backend server. 
It allows executing model chats, maintaining context, and executing **Local Tools** (such as `list_dir`, `read_file`, and `run_command`) on your laptop locally while querying the brain in the cloud.

---

## 🚀 Setup & Testing

### 1. Start your Python Backend (FastAPI)
First, run your Backend API on your server (or locally for testing):

```bash
cd backend
pip install fastapi uvicorn requests pydantic
uvicorn app:app --reload --port 8000
```
*(Your backend uses `OpenRouterClient` connected to your `.env` API keys).*

---

### 2. Test the CLI locally

Navigate to the `cli` folder and install NPM packages:

```bash
cd cli
npm install
node index.js
```

---

## 🌍 Global Distribution (Publishing to NPM)

When your Backend is hosted on a live URL (e.g., Render, Railway, or VPS):

1. **Update `.env` in `cli/`**: Change `BACKEND_URL` to point to your live URL.
2. **Login to NPM**:
   ```bash
   npm login
   ```
3. **Publish to package registry**:
   ```bash
   npm publish
   ```

🎉 **Now anyone can run:**
```cmd
npx rathi-cli "message here"
```
Or install it globally:
```cmd
npm install -g rathi-cli
rathi
```
*(It links `rathi` globally because of the `"bin"` mapping in `package.json`)*
