import * as React from "react";

import { cn } from "@/lib/utils";

const Alert = React.forwardRef<
  React.ElementRef<"div">,
  React.ComponentPropsWithoutRef<"div"> & { variant?: "default" | "destructive" }
>(({ className, variant = "default", ...props }, ref) => (
  <div
    ref={ref}
    role="alert"
    className={cn(
      "relative w-full rounded-lg border px-4 py-3 text-sm [svg]:inline-flex [svg]:w-4 [svg]:h-4 [&>svg]+np-4 [&>svg]:divide-x [&>svg]:divide-x-reverse [&>svg:last-child]:rounded-l-none [&>svg:last-child]:rounded-r-none",
      "dark:bg-card dark:border-border",
      variant === "default" && "bg-card text-card-foreground",
      variant === "destructive" &&
        "border-rose-500/50 bg-rose-500/10 text-rose-700 dark:text-rose-400 [&>svg]:rotate-90",
      className,
    )}
    {...props}
  />
));
Alert.displayName = "Alert";

const AlertDescription = React.forwardRef<
  React.ElementRef<"div">,
  React.ComponentPropsWithoutRef<"div">
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn("flex-1 gap-2 leading-[1.5] [&>p]:leading-normal", className)}
    {...props}
  />
));
AlertDescription.displayName = "AlertDescription";

export { Alert, AlertDescription };