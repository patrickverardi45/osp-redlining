import "./globals.css";
import "leaflet/dist/leaflet.css";

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          padding: 0,
          background: "#0b0f17",
          color: "#e6ecf5",
        }}
      >
        {children}
      </body>
    </html>
  );
}
