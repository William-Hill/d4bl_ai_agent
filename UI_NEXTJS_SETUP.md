# Next.js UI Setup Guide

This guide explains how to use the new Next.js-based UI instead of the vanilla JavaScript version.

## Why Next.js?

✅ **Better Architecture**: Component-based React architecture  
✅ **Type Safety**: Full TypeScript support  
✅ **Better DX**: Hot reload, better tooling, easier debugging  
✅ **Production Ready**: Optimized builds, SSR capabilities  
✅ **Scalability**: Easier to add features and maintain  
✅ **Ecosystem**: Access to React ecosystem and libraries  

## Quick Start

### Option 1: Run Both Servers Separately (Recommended for Development)

1. **Terminal 1 - Start FastAPI Backend**:
   ```bash
   python run_ui.py
   # Backend runs on http://localhost:8000
   ```

2. **Terminal 2 - Start Next.js Frontend**:
   ```bash
   cd ui-nextjs
   npm install
   npm run dev
   # Frontend runs on http://localhost:3000
   ```

3. **Open Browser**: Navigate to `http://localhost:3000`

### Option 2: Use Next.js API Routes (Advanced)

You can also integrate the FastAPI backend directly into Next.js using API routes, but the current setup uses a separate backend which is more flexible.

## Project Structure

```
d4bl_ai_agent/
├── ui/                    # Vanilla JS UI (original)
├── ui-nextjs/             # Next.js UI (new)
│   ├── app/              # Next.js App Router
│   ├── components/       # React components
│   ├── hooks/            # Custom hooks
│   └── lib/              # Utilities
├── src/d4bl/
│   └── api.py            # FastAPI backend
└── run_ui.py             # Backend server script
```

## Migration Notes

The Next.js UI provides the same functionality as the vanilla JS version but with:

- **Better code organization**: Components are separated and reusable
- **Type safety**: TypeScript catches errors at compile time
- **Better state management**: React hooks for cleaner state handling
- **Improved performance**: Next.js optimizations and code splitting
- **Better developer experience**: Hot reload, better error messages

## Deployment

### Development
- Backend: `python run_ui.py` (port 8000)
- Frontend: `cd ui-nextjs && npm run dev` (port 3000)

### Production
- Build Next.js: `cd ui-nextjs && npm run build && npm start`
- Or use Docker Compose (see main README)

## Choosing Between UIs

**Use Vanilla JS UI (`ui/`)** if:
- You want zero build step
- You prefer simple HTML/CSS/JS
- You don't need React features

**Use Next.js UI (`ui-nextjs/`)** if:
- You want better code organization
- You plan to add more features
- You want TypeScript support
- You prefer modern React patterns
- You want better performance optimizations

Both UIs work with the same FastAPI backend!

