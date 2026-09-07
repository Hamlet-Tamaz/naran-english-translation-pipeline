export const metadata = {
  title: 'Naran Pipeline',
  description: 'Armenian content translation pipeline',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body style={{ margin: 0, fontFamily: 'system-ui, -apple-system, sans-serif', background: '#0a0a0f', color: '#e4e4e7' }}>
        {children}
      </body>
    </html>
  )
}
