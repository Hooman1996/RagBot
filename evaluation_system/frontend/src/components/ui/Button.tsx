import type { ButtonHTMLAttributes, PropsWithChildren } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";

export function Button({ variant = "primary", className = "", children, ...props }: PropsWithChildren<ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }>) {
  return <button className={`button button--${variant} ${className}`} {...props}>{children}</button>;
}
