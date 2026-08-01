import type { ReactNode } from "react";
import { cleanup, render, screen, fireEvent, waitFor } from "@testing-library/react";
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
  transactionTotalPages?: number;
  transactions?: Array<{
    id: number;
    type: string;
    exchange_leg?: "debit" | "credit" | null;
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
  transactionTotalPages = 1,
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

    if (url.startsWith("/transactions?page=")) {
      const query = new URLSearchParams(url.split("?")[1]);
      const page = Number(query.get("page") ?? "1");

      return Promise.resolve({
        data: {
          items: transactions,
          page,
          page_size: 5,
          total: transactions.length,
          total_pages: transactionTotalPages,
        },
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
    expect(screen.getAllByText("$1250.50").length).toBeGreaterThanOrEqual(1);

    expect(screen.getByText("Cash LBP")).toBeInTheDocument();
    expect(screen.getByText(/2,000,000/)).toBeInTheDocument();

    expect(screen.getByText("1 USD = 89,500 LBP")).toBeInTheDocument();

    expect(screen.getAllByText("Food").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Transport")).toBeInTheDocument();
    expect(screen.getByTestId("pie-chart")).toBeInTheDocument();

    expect(screen.getByText("Alice")).toBeInTheDocument();
    expect(screen.getByText("-25 USD")).toBeInTheDocument();

    expect(apiGetMock).toHaveBeenCalledWith("/accounts/balance");
    expect(apiGetMock).toHaveBeenCalledWith(
      "/transactions?page=1&page_size=5"
    );
    expect(apiGetMock).toHaveBeenCalledWith("/exchange/rates");
    expect(apiGetMock).not.toHaveBeenCalledWith("/exchange/rates/live");
    expect(apiGetMock).toHaveBeenCalledWith(
      expect.stringMatching(/^\/transactions\/summary\?month=\d{4}-\d{2}$/)
    );
  });


  it("loads the next page of recent transactions", async () => {
    mockSuccessfulDashboardRequests({
      transactionTotalPages: 3,
      transactions: [
        {
          id: 1,
          type: "receive",
          amount: 10,
          currency: "USD",
          counterparty_name: "Test User",
          category: "Other",
          status: "completed",
          created_at: new Date().toISOString(),
        },
      ],
    });

    render(<DashboardPage />);

    expect(
      await screen.findByText("Page 1 of 3")
    ).toBeInTheDocument();

    const previousButton = screen.getByRole("button", {
      name: "Previous transaction page",
    });
    const nextButton = screen.getByRole("button", {
      name: "Next transaction page",
    });

    expect(previousButton).toBeDisabled();
    expect(nextButton).toBeEnabled();

    fireEvent.click(nextButton);

    await waitFor(() => {
      expect(apiGetMock).toHaveBeenCalledWith(
        "/transactions?page=2&page_size=5"
      );
    });

    expect(screen.getByText("Page 2 of 3")).toBeInTheDocument();
    expect(previousButton).toBeEnabled();
  });

  it("shows exchange debit and credit legs with correct signs", async () => {
    mockSuccessfulDashboardRequests({
      transactions: [
        {
          id: 11,
          type: "exchange",
          exchange_leg: "debit",
          amount: 25,
          currency: "USD",
          counterparty_name: null,
          category: "Exchange",
          status: "completed",
          created_at: new Date().toISOString(),
        },
        {
          id: 12,
          type: "exchange",
          exchange_leg: "credit",
          amount: 2237500,
          currency: "LBP",
          counterparty_name: null,
          category: "Exchange",
          status: "completed",
          created_at: new Date().toISOString(),
        },
      ],
    });

    render(<DashboardPage />);

    expect(await screen.findByText("Exchange debit")).toBeInTheDocument();
    expect(screen.getByText("-25 USD")).toBeInTheDocument();

    expect(screen.getByText("Exchange credit")).toBeInTheDocument();
    expect(screen.getByText("+2237500 LBP")).toBeInTheDocument();
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

    expect(screen.getByText("Fresh USD")).toBeInTheDocument();
    expect(screen.getByText("Cash LBP")).toBeInTheDocument();
    expect(screen.getByText("$0.00")).toBeInTheDocument();
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
