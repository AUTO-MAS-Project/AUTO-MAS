/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BannerGame } from './BannerGame';
import type { BannerRegion } from './BannerRegion';
import type { BannerSourceStatus } from './BannerSourceStatus';
import type { CalendarBanner } from './CalendarBanner';
export type BannerWatchOut = {
    games: Array<BannerGame>;
    subscriptions: Array<BannerRegion>;
    subscriptionRevision: number;
    banners: Array<CalendarBanner>;
    sources: Array<BannerSourceStatus>;
    hasNotificationChannels: boolean;
};
