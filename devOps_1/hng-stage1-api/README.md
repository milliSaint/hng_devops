# HNG Stage 1 — Personal API

A minimal REST API built with Node.js and Express, deployed on a Linux VPS behind Nginx.

## How to Run Locally

```bash
npm install
npm start
```

The server starts on port `3000` by default.

## Endpoints

### GET /
Returns a simple status message.

```json
{ "message": "API is running" }
```

### GET /health
Returns the health status of the API.

```json
{ "message": "healthy" }
```

### GET /me
Returns personal details.

```json
{
  "name": "Saint Oise",
  "email": "millicent.facebook@gmail.com",
  "github": "https://github.com/unicornoceanldadev"
}
```

## Live Deployment

**Base URL:** https://hngdevops.unicornocean.ai
