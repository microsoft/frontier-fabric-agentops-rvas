"use client";
import { FluentProvider, webLightTheme } from "@fluentui/react-components";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <FluentProvider theme={webLightTheme}>
      {children}
    </FluentProvider>
  );
}
