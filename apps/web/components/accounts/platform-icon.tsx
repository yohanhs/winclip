"use client";

import type { AccountPlatform } from "@winclip/api-client";

interface PlatformIconProps {
  platform: AccountPlatform;
  className?: string;
}

export function PlatformIcon({
  platform,
  className = "size-4",
}: PlatformIconProps) {
  if (platform === "youtube") {
    return (
      <svg viewBox="0 0 24 24" className={className} fill="none" aria-hidden="true">
        <rect x="2" y="4.5" width="20" height="15" rx="4" fill="#EF4444" />
        <path d="M10 9.2L15.4 12L10 14.8V9.2Z" fill="#FFFFFF" />
      </svg>
    );
  }
  if (platform === "tiktok") {
    return (
      <svg viewBox="0 0 24 24" className={className} fill="none" aria-hidden="true">
        <rect
          x="2"
          y="2"
          width="20"
          height="20"
          rx="5"
          fill="#18181B"
          stroke="rgba(255,255,255,0.14)"
        />
        <path
          d="M15.6 8.35C14.7 7.8 14.1 6.85 13.95 5.75H12.05V14.4C12.05 15.5 11.15 16.4 10.05 16.4C8.95 16.4 8.05 15.5 8.05 14.4C8.05 13.3 8.95 12.4 10.05 12.4C10.3 12.4 10.55 12.45 10.75 12.55V10.6C10.5 10.55 10.28 10.53 10.05 10.53C7.9 10.53 6.15 12.28 6.15 14.43C6.15 16.58 7.9 18.33 10.05 18.33C12.2 18.33 13.95 16.58 13.95 14.43V9.95C14.75 10.53 15.72 10.88 16.78 10.88V8.98C16.35 8.98 15.95 8.58 15.6 8.35Z"
          fill="#22D3EE"
          transform="translate(-0.4, -0.3)"
        />
        <path
          d="M15.6 8.35C14.7 7.8 14.1 6.85 13.95 5.75H12.05V14.4C12.05 15.5 11.15 16.4 10.05 16.4C8.95 16.4 8.05 15.5 8.05 14.4C8.05 13.3 8.95 12.4 10.05 12.4C10.3 12.4 10.55 12.45 10.75 12.55V10.6C10.5 10.55 10.28 10.53 10.05 10.53C7.9 10.53 6.15 12.28 6.15 14.43C6.15 16.58 7.9 18.33 10.05 18.33C12.2 18.33 13.95 16.58 13.95 14.43V9.95C14.75 10.53 15.72 10.88 16.78 10.88V8.98C16.35 8.98 15.95 8.58 15.6 8.35Z"
          fill="#FFFFFF"
        />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" aria-hidden="true">
      <rect x="2.5" y="2.5" width="19" height="19" rx="5.5" fill="#EA580C" />
      <rect
        x="6.5"
        y="6.5"
        width="11"
        height="11"
        rx="3.2"
        stroke="#FFFFFF"
        strokeWidth="1.7"
      />
      <circle cx="12" cy="12" r="2.6" stroke="#FFFFFF" strokeWidth="1.7" />
      <circle cx="15.3" cy="8.7" r="0.9" fill="#FFFFFF" />
    </svg>
  );
}

export function platformTitle(platform: AccountPlatform): string {
  switch (platform) {
    case "youtube":
      return "YouTube";
    case "tiktok":
      return "TikTok";
    case "instagram":
      return "Instagram";
  }
}

export function platformAccent(platform: AccountPlatform): string {
  switch (platform) {
    case "youtube":
      return "#EF4444";
    case "tiktok":
      return "#06B6D4";
    case "instagram":
      return "#F97316";
  }
}
