import clsx from "clsx";
import { EmptyState, Table, Tbody, Td, Th, Thead, Tr } from "@/components/ui";
import { fmtNum, polarity, type SimPosition } from "@/lib/api";

/** Portfolio holdings with cost/value/P&L/allocation (Phase 6, shared). */
export function HoldingsTable({ positions }: { positions: SimPosition[] }) {
  if (positions.length === 0) {
    return <EmptyState title="No positions yet" description="Place an order to start building the portfolio." />;
  }
  return (
    <Table minWidth="560px">
      <Thead>
        <tr>
          <Th>Symbol</Th>
          <Th numeric>Qty</Th>
          <Th numeric>Avg cost</Th>
          <Th numeric>Last</Th>
          <Th numeric>Value</Th>
          <Th numeric>Unreal. P&amp;L</Th>
          <Th numeric>Alloc</Th>
        </tr>
      </Thead>
      <Tbody>
        {positions.map((pos) => (
          <Tr key={pos.symbol}>
            <Td className="font-medium text-ink">{pos.symbol}</Td>
            <Td numeric>{pos.qty}</Td>
            <Td numeric>{fmtNum(pos.avg_cost)}</Td>
            <Td numeric>{fmtNum(pos.last_price)}</Td>
            <Td numeric>{fmtNum(pos.market_value)}</Td>
            <Td numeric className={polarity(pos.unrealized_pnl)}>{fmtNum(pos.unrealized_pnl)}</Td>
            <Td numeric>{pos.allocation_pct.toFixed(1)}%</Td>
          </Tr>
        ))}
      </Tbody>
    </Table>
  );
}
