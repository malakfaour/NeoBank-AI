import type { ReactNode } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { apiGetMock, routerPushMock } = vi.hoisted(() => ({
  apiGetMock: vi.fn(),
  routerPushMock: vi.fn(),
}));

vi.mock("@/lib/axios", () => ({
  default: {
    get: apiGetMock,
  },
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: routerPushMock,
  }),
}));

// Recharts depends on browser layout APIs that jsdom does not provide.
// These lightweight replacements let us test the dashboard data and states.
vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children?: ReactNode }) => (
    <div data-testid="responsive-container">{children}</div>
  ),
  PieChart: ({ children }: { children?: ReactNode }) => (
    <div data-testid="pie-chart">{children}</div>
  ),
  Pie: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  Cell: () => <span data-testid="chart-cell" />,
  Tooltip: () => null,
  Legend: () => null,
}));

import DashboardPage from "@/app/(dashboard)/dashboard/page";
import { useAuthStore } from "@/store/authStore";

interface DashboardMockData {
  balances?: Array<{
    currency: string;
    balance: number;
    account_number: string | null;
    iban: string | null;
  }>;
  transactions?: Array<{
    id: number;
    type: "send" | "receive";
    amount: number;
    currency: string;
    counterparty_name: string | null;
    category: string | null;
    status: string;
    created_at: string;
  }>;
  exchangeRates?: Array<{
    base_currency: string;
    target_currency: string;
    rate: string | number;
    provider: string;
    last_updated_at: string | null;
  }>;
  summary?: Array<{
    category: string | null;
    currency: string;
    total_amount: number;
    transaction_count: number;
  }>;
}

function mockSuccessfulDashboardRequests({
  balances = [],
  transactions = [],
  exchangeRates = [
    {
      base_currency: "USD",
      target_currency: "LBP",
      rate: "89500",
      provider: "test-provider",
      last_updated_at: null,
    },
  ],
  summary = [],
}: DashboardMockData) {
  apiGetMock.mockImplementation((url: string) => {
    if (url === "/accounts/balance") {
      return Promise.resolve({
        data: { balances },
      });
    }

    if (url === "/transactions?page_size=5") {
      return Promise.resolve({
        data: { items: transactions },
      });
    }

    if (url === "/exchange/rates") {
      return Promise.resolve({
        data: exchangeRates,
      });
    }

    if (url.startsWith("/transactions/summary?month=")) {
      return Promise.resolve({
        data: { summary },
      });
    }

    return Promise.reject(new Error(`Unexpected API request: ${url}`));
  });
}

describe("DashboardPage", () => {
  beforeEach(() => {
    apiGetMock.mockReset();
    routerPushMock.mockReset();

    useAuthStore.setState({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
    });
  });

  afterEach(() => {
    cleanup();
  });

  it("renders balance cards, spending chart, and transaction feed", async () => {
    mockSuccessfulDashboardRequests({
      balances: [
        {
          currency: "USD",
          balance: 1250.5,
          account_number: "USD-001",
          iban: "LB120000000000000000000001",
        },
        {
          currency: "LBP",
          balance: 2000000,
          account_number: "LBP-001",
          iban: "LB120000000000000000000002",
        },
      ],
      transactions: [
        {
          id: 1,
          type: "send",
          amount: 25,
          currency: "USD",
          counterparty_name: "Alice",
          category: "Food",
          status: "completed",
          created_at: new Date().toISOString(),
        },
      ],
      exchangeRates: [
        {
          base_currency: "USD",
          target_currency: "LBP",
          rate: "89500",
          provider: "test-provider",
          last_updated_at: new Date().toISOString(),
        },
      ],
      summary: [
        {
          category: "Food",
          currency: "USD",
          total_amount: 50,
          transaction_count: 2,
        },
        {
          category: "Transport",
          currency: "USD",
          total_amount: 20,
          transaction_count: 1,
        },
      ],
    });

    render(<DashboardPage />);

    expect(await screen.findByText("Fresh USD")).toBeInTheDocument();
    expect(screen.getByText("$1250.50")).toBeInTheDocument();

    expect(screen.getByText("Cash LBP")).toBeInTheDocument();
    expect(screen.getByText(/2,000,000/)).toBeInTheDocument();

    expect(screen.getByText("1 USD = 89,500 LBP")).toBeInTheDocument();

    expect(screen.getAllByText("Food").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Transport")).toBeInTheDocument();
    expect(screen.getByTestId("pie-chart")).toBeInTheDocument();

    expect(screen.getByText("Alice")).toBeInTheDocument();
    expect(screen.getByText("-25 USD")).toBeInTheDocument();

    expect(apiGetMock).toHaveBeenCalledWith("/accounts/balance");
    expect(apiGetMock).toHaveBeenCalledWith("/transactions?page_size=5");
    expect(apiGetMock).toHaveBeenCalledWith("/exchange/rates");
    expect(apiGetMock).not.toHaveBeenCalledWith("/exchange/rates/live");
    expect(apiGetMock).toHaveBeenCalledWith(
      expect.stringMatching(/^\/transactions\/summary\?month=\d{4}-\d{2}$/)
    );
  });

  it("renders empty states when the API returns no dashboard data", async () => {
    mockSuccessfulDashboardRequests({});

    render(<DashboardPage />);

    expect(
      await screen.findByText("No spending data yet this month")
    ).toBeInTheDocument();

    expect(screen.getByText("No transactions yet")).toBeInTheDocument();

    expect(
      screen.getByText("Make a transaction to see your breakdown")
    ).toBeInTheDocument();

    expect(screen.queryByText("Fresh USD")).not.toBeInTheDocument();
    expect(screen.queryByTestId("pie-chart")).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    expect(apiGetMock).toHaveBeenCalledTimes(4);
  });

  it("renders an error state when dashboard API requests fail", async () => {
    apiGetMock.mockRejectedValue(new Error("Network unavailable"));

    render(<DashboardPage />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Some dashboard data could not be loaded. Please try again."
    );

    expect(
      screen.getByText("No spending data yet this month")
    ).toBeInTheDocument();

    expect(screen.getByText("No transactions yet")).toBeInTheDocument();
    expect(apiGetMock).toHaveBeenCalledTimes(4);
  });
});
