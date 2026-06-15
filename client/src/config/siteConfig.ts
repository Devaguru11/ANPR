import siteConfigJson from "../../../config/site.config.json";

export type SiteTimezoneBlock = {
  iana: string;
  sqlOffset: string;
  label: string;
};

export type SiteConfig = {
  locale: string;
  region: { label: string; countryCode: string };
  timezone: {
    db: SiteTimezoneBlock;
    display: SiteTimezoneBlock;
    displayHoursAheadOfDb: number;
  };
  cameraOnlineStaleMinutes: number;
};

export const SITE_CONFIG = siteConfigJson as SiteConfig;

export const SITE_TIMEZONE = SITE_CONFIG.timezone.display.iana;
export const DB_TIMEZONE = SITE_CONFIG.timezone.db.iana;
