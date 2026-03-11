import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'FireReach — Autonomous Outreach Engine',
  description:
    'FireReach harvests live buyer-intent signals, resolves decision-maker contacts, and sends hyper-personalised cold emails — fully autonomous, zero cost.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
