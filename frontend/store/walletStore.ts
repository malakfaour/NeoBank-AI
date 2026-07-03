import { create } from "zustand";
import { devtools } from "zustand/middleware";

interface Wallet {
  id: string;
  currency: "USD" | "LBP";
  balance: number;
  updated_at: string;
}

interface WalletState {
  wallets: Wallet[];
  isLoading: boolean;
  setWallets: (wallets: Wallet[]) => void;
  setLoading: (loading: boolean) => void;
  getWalletByCurrency: (currency: "USD" | "LBP") => Wallet | undefined;
}

export const useWalletStore = create<WalletState>()(
  devtools(
    (set, get) => ({
      wallets: [],
      isLoading: false,
      setWallets: (wallets) => set({ wallets }, false, "setWallets"),
      setLoading: (isLoading) => set({ isLoading }, false, "setLoading"),
      getWalletByCurrency: (currency) =>
        get().wallets.find((w) => w.currency === currency),
    }),
    { name: "WalletStore", enabled: process.env.NODE_ENV === "development" }
  )
);
