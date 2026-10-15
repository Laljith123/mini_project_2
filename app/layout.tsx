import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "College Admission Enquiry Assistant",
  description:
    "An intelligent admission enquiry assistant powered by GPT and grounded in verified college admissions data.",
  icons: {
    icon: "/logo.png",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <header className="site-header">
          <div className="brand">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/logo.png" alt="College logo" width={52} height={52} />
            <div>
              <h1>College Admission Enquiry Assistant</h1>
              <p className="tagline">
                Powered by GPT &middot; eligibility &middot; courses &middot;
                fees &middot; procedure &middot; facilities
              </p>
            </div>
          </div>
          <nav>
            <Link href="/">Ask a question</Link>
            <Link href="/kb">Knowledge base</Link>
          </nav>
        </header>
        <main>{children}</main>
        <footer>
          <p>
            College Admission Enquiry Assistant &middot; Mini Project &middot;
            Department of CSE
          </p>
        </footer>
      </body>
    </html>
  );
}
