/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_CLERK_PUBLISHABLE_KEY: string
  // Add more env variables here as needed
}

interface ImportMeta {
  readonly env: ImportMetaEnv
} 