/**
 * @file classNames.ts
 * @description Conditional class-name merge for Tailwind components.
 *
 * `clsx` folds the conditional class arguments into one class string and
 * `tailwind-merge` resolves conflicting Tailwind utilities, so the last
 * utility of a conflicting pair wins. One implementation shared by every
 * component that composes class names.
 */

import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
