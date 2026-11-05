export const QUEUE_WEEKDAYS: readonly string[] = [
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
  'Sunday',
]

export const areAllWeekdaysSelected = (days: readonly string[]) =>
  QUEUE_WEEKDAYS.every(day => days.includes(day))
