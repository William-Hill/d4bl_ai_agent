# D4BL AI Agent - Next.js UI

Modern React/Next.js frontend for the D4BL AI Agent research tool.

## Features

- ⚡ **Next.js 16** with App Router
- ⚛️ **React 19** with TypeScript
- 🎨 **Tailwind CSS** for styling
- 🔄 **Real-time WebSocket** updates
- 📱 **Responsive Design**
- 🚀 **Production Ready**

## Getting Started

### Prerequisites

- Node.js 18+ and npm
- FastAPI backend running (see main project README)

### Development

1. **Install dependencies**:
   ```bash
   npm install
   ```

2. **Set up environment variables** (optional for local dev):
   ```bash
   cp .env.local.example .env.local
   # Edit .env.local if needed
   ```

3. **Start the development server**:
   ```bash
   npm run dev
   ```

4. **Open your browser**:
   Navigate to [http://localhost:3000](http://localhost:3000)

The Next.js app will proxy API requests to the FastAPI backend running on port 8000.

### Production Build

1. **Build the application**:
   ```bash
   npm run build
   ```

2. **Start the production server**:
   ```bash
   npm start
   ```

## Project Structure

```
ui-nextjs/
├── app/                 # Next.js App Router
│   ├── layout.tsx      # Root layout
│   ├── page.tsx        # Home page
│   └── globals.css     # Global styles
├── components/         # React components
│   ├── ResearchForm.tsx
│   ├── ProgressCard.tsx
│   ├── ResultsCard.tsx
│   └── ErrorCard.tsx
├── hooks/              # Custom React hooks
│   └── useWebSocket.ts
├── lib/                # Utilities
│   └── api.ts          # API client
└── public/             # Static assets
```

## Configuration

### Environment Variables

Create a `.env.local` file in the `ui-nextjs` directory:

```bash
# Backend API URL (optional - defaults to http://localhost:8000)
# For local development, leave this empty to use Next.js rewrites
# For production, set this to your deployed backend URL
NEXT_PUBLIC_API_URL=http://localhost:8000
```

**Note**: 
- If `NEXT_PUBLIC_API_URL` is not set, Next.js will proxy `/api/*` requests to `http://localhost:8000`
- WebSocket connections always connect directly to the backend (Next.js doesn't proxy WebSockets)

### API Integration

The frontend communicates with the FastAPI backend via:
- REST API: `/api/*` endpoints
- WebSocket: `/ws/*` for real-time updates

## Deployment

### Vercel (Recommended)

1. Push your code to GitHub
2. Import project in Vercel
3. Set environment variables
4. Deploy!

### Docker

See the main project's `Dockerfile` and `docker-compose.yml` for containerized deployment.

### Other Platforms

Next.js can be deployed to any platform that supports Node.js:
- Netlify
- AWS Amplify
- Railway
- Render
- etc.

## Development Tips

- The app uses Next.js rewrites to proxy API requests in development
- WebSocket connections automatically reconnect on disconnect
- TypeScript provides type safety throughout the codebase
- Tailwind CSS classes are used for all styling

## Learn More

- [Next.js Documentation](https://nextjs.org/docs)
- [React Documentation](https://react.dev)
- [Tailwind CSS Documentation](https://tailwindcss.com/docs)
