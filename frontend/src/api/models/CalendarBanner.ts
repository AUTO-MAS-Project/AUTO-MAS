/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type CalendarBanner = {
    id: string;
    game: string;
    server: string;
    title: string;
    kind: string;
    start_mode: CalendarBanner.start_mode;
    starts_at: (string | null);
    ends_at: (string | null);
    end_kind?: CalendarBanner.end_kind;
    confirmed_open_at: (string | null);
    official_url: string;
    verified_at: string;
    status: CalendarBanner.status;
    stale: boolean;
};
export namespace CalendarBanner {
    export enum start_mode {
        SCHEDULED = 'scheduled',
        AFTER_MAINTENANCE = 'after_maintenance',
        TBD = 'tbd',
    }
    export enum end_kind {
        KNOWN = 'known',
        PERMANENT = 'permanent',
        UNKNOWN = 'unknown',
    }
    export enum status {
        PENDING = 'pending',
        ANNOUNCED = 'announced',
        OPEN = 'open',
        ENDED = 'ended',
        CANCELLED = 'cancelled',
    }
}
