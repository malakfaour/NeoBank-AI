import { getPostAuthDestination } from "@/lib/postAuthNavigation";

export function hasStoredAccountSession(storage: Pick<Storage, "getItem">): boolean {
  return Boolean(storage.getItem("access_token") || storage.getItem("refresh_token"));
}

export async function getStartupDestination(
  storage: Pick<Storage, "getItem">,
  resolveDestination = getPostAuthDestination
): Promise<string> {
  if (!hasStoredAccountSession(storage)) return "/login";
  return resolveDestination();
}
