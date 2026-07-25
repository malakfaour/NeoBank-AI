import { loadStripe, type Stripe } from "@stripe/stripe-js";

// DEVATTECH-131: singleton so we don't re-initialize Stripe.js on every
// render of a component that needs it. The publishable key is safe to
// expose client-side by design (unlike the secret key, which never leaves
// the backend).
let stripePromise: Promise<Stripe | null> | null = null;

export function getStripe(): Promise<Stripe | null> {
  if (!stripePromise) {
    const key = process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY;
    if (!key) {
      console.error(
        "NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY is not set -- card top-up will fail. Add it to frontend/.env.local."
      );
    }
    stripePromise = loadStripe(key ?? "");
  }
  return stripePromise;
}