import * as ed from "@noble/ed25519";

const PRIVATE_KEY_STORAGE = "neo_biometric_private_key";
const DEVICE_ID_STORAGE = "neo_biometric_device_id";

export function getDeviceId(): string {
  let id = localStorage.getItem(DEVICE_ID_STORAGE);
  if (!id) {
    id = `device_${Date.now()}_${Math.random().toString(36).slice(2)}`;
    localStorage.setItem(DEVICE_ID_STORAGE, id);
  }
  return id;
}

export function isBiometricEnrolled(): boolean {
  return !!localStorage.getItem(PRIVATE_KEY_STORAGE);
}

export async function generateKeyPair(): Promise<{ privateKeyHex: string; publicKeyPem: string }> {
  const privateKey = crypto.getRandomValues(new Uint8Array(32));
  const publicKey = await ed.getPublicKeyAsync(privateKey);
  const privateKeyHex = Array.from(privateKey).map(b => b.toString(16).padStart(2, "0")).join("");
  const publicKeyBase64 = btoa(String.fromCharCode(...publicKey));
  const publicKeyPem = `-----BEGIN PUBLIC KEY-----\n${publicKeyBase64}\n-----END PUBLIC KEY-----`;
  return { privateKeyHex, publicKeyPem };
}

export async function signNonce(nonce: string): Promise<string> {
  const privateKeyHex = localStorage.getItem(PRIVATE_KEY_STORAGE);
  if (!privateKeyHex) throw new Error("No biometric key found");
  const privateKey = Uint8Array.from(privateKeyHex.match(/.{1,2}/g)!.map(b => parseInt(b, 16)));
  const message = new TextEncoder().encode(nonce);
  const signature = await ed.signAsync(message, privateKey);
  return btoa(String.fromCharCode(...signature));
}

export function savePrivateKey(privateKeyHex: string): void {
  localStorage.setItem(PRIVATE_KEY_STORAGE, privateKeyHex);
}

export function clearBiometricKey(): void {
  localStorage.removeItem(PRIVATE_KEY_STORAGE);
  localStorage.removeItem(DEVICE_ID_STORAGE);
}