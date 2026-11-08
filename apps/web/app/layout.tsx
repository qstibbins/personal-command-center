import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = { title: "Personal Command Center", description: "Capture to action" };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
