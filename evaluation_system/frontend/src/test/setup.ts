import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => cleanup());

Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
  configurable: true,
  value() { this.setAttribute("open", ""); },
});
Object.defineProperty(HTMLDialogElement.prototype, "close", {
  configurable: true,
  value() { this.removeAttribute("open"); this.dispatchEvent(new Event("close")); },
});
