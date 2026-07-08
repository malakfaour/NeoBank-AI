import { useCallback, useEffect } from "react";
import { useWalletStore } from "@/store/walletStore";
import api from "@/lib/axios";

export function useWallets() {
  const { wallets, isLoading, setWallets, setLoading } = useWalletStore();

  const fetchWallets = useCallback(async () => {
    setLoading(true);
    try {
     const res = await api.get("/accounts/balance");
setWallets(res.data.balances ?? []);
    } finally {
      setLoading(false);
    }
  }, [setWallets, setLoading]);

  useEffect(() => {
    fetchWallets();
  }, [fetchWallets]);

  return { wallets, isLoading, refetch: fetchWallets };
}