import {
  Badge,
  Box,
  Button,
  Card,
  Flex,
  Heading,
  IconButton,
  RadioCards,
  Select,
  Spinner,
  Text,
} from '@radix-ui/themes';
import { useId, useMemo, useState } from 'react';
import { useLocation, useNavigation, useSearchParams } from 'react-router';
import type { AvailableTime, Doctor } from '../../appointments/api';
import {
  addDays,
  DAY_PART_LABELS,
  dateKey,
  dayPart,
  formatDateTime,
  formatDay,
  formatDayOfMonth,
  formatTime,
  formatWeekdayShort,
  formatWeekRange,
  mondayOf,
  type DayPart,
} from '../../appointments/time';
import { ALL_DOCTORS, type BrowserData } from '../../appointments/availability';
import {
  ArrowRightIcon,
  CalendarEmptyIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  ClockIcon,
} from '../icons';
import './AvailabilityBrowser.css';

/** All doctors free at one start time. */
export type TimeOption = { startsAt: string; endsAt: string; doctors: Doctor[] };

type Props = {
  data: BrowserData;
  /** Called with the chosen start time; the dialog then asks for the remaining details. */
  onSelect: (option: TimeOption) => void;
};

function groupByDay(times: AvailableTime[]): Map<string, TimeOption[]> {
  const days = new Map<string, Map<string, TimeOption>>();
  for (const time of times) {
    const day = dateKey(new Date(time.startsAt));
    const options = days.get(day) ?? new Map<string, TimeOption>();
    const option = options.get(time.startsAt) ?? {
      startsAt: time.startsAt,
      endsAt: time.endsAt,
      doctors: [],
    };
    option.doctors.push(time.doctor);
    options.set(time.startsAt, option);
    days.set(day, options);
  }
  return new Map([...days].map(([day, options]) => [day, [...options.values()]]));
}

const toOption = (time: AvailableTime): TimeOption => ({
  startsAt: time.startsAt,
  endsAt: time.endsAt,
  doctors: [time.doctor],
});

/**
 * Week view of the available times (A07): doctor filter, week navigation, one card per day and
 * the free start times of the chosen day, grouped into morning, afternoon and evening.
 */
export function AvailabilityBrowser({ data, onSelect }: Props) {
  const [params, setParams] = useSearchParams();
  const { pathname } = useLocation();
  const navigation = useNavigation();
  const loading = navigation.state === 'loading' && navigation.location.pathname === pathname;
  const doctorLabelId = useId();

  const go = (changes: { week?: string; doctor?: string }) => {
    const next = new URLSearchParams(params);
    if (changes.week) next.set('week', changes.week);
    if (changes.doctor) next.set('doctor', changes.doctor);
    setParams(next, { preventScrollReset: true });
  };

  const allDoctors = data.doctor === ALL_DOCTORS;

  return (
    <Flex direction="column" gap="5">
      {data.doctors.length > 0 && (
        <Flex direction={{ initial: 'column', sm: 'row' }} gap="2" align={{ sm: 'center' }}>
          <Text id={doctorLabelId} size="2" weight="medium" className="availability__label">
            Ärztin oder Arzt
          </Text>
          <Select.Root value={data.doctor} onValueChange={(doctor) => go({ doctor })} size="3">
            <Select.Trigger
              aria-labelledby={doctorLabelId}
              className="availability__doctor"
              placeholder="Alle Ärztinnen und Ärzte"
            />
            <Select.Content position="popper">
              <Select.Item value={ALL_DOCTORS}>Alle Ärztinnen und Ärzte</Select.Item>
              {data.doctors.map((doctor) => (
                <Select.Item key={doctor.id} value={doctor.id}>
                  {doctor.displayName}
                </Select.Item>
              ))}
            </Select.Content>
          </Select.Root>
        </Flex>
      )}

      {data.next && (
        <NextAvailable
          time={data.next}
          today={data.today}
          showDoctor={allDoctors}
          onSelect={() => data.next && onSelect(toOption(data.next))}
        />
      )}

      <Card size={{ initial: '2', sm: '3' }}>
        <Flex direction="column" gap="5">
          <Flex justify="between" align="center" gap="3">
            <IconButton
              variant="soft"
              color="gray"
              size="3"
              aria-label="Vorherige Woche"
              disabled={data.week <= data.firstWeek}
              onClick={() => go({ week: addDays(data.week, -7) })}
            >
              <ChevronLeftIcon size={20} />
            </IconButton>
            <Flex direction="column" align="center" gap="1">
              <Heading as="h2" size="4" aria-live="polite">
                {formatWeekRange(data.week)}
              </Heading>
              {data.week !== data.firstWeek ? (
                <Button variant="ghost" size="1" onClick={() => go({ week: data.firstWeek })}>
                  Zur aktuellen Woche
                </Button>
              ) : (
                <Text size="1" color="gray">
                  Diese Woche
                </Text>
              )}
            </Flex>
            <IconButton
              variant="soft"
              color="gray"
              size="3"
              aria-label="Nächste Woche"
              disabled={data.week >= data.lastWeek}
              onClick={() => go({ week: addDays(data.week, 7) })}
            >
              <ChevronRightIcon size={20} />
            </IconButton>
          </Flex>

          <Box className="availability__week" aria-busy={loading || undefined}>
            {loading && (
              <Flex className="availability__loading" justify="center" align="center">
                <Spinner size="3" />
              </Flex>
            )}
            {/* Remounts per week and doctor, so the first free day is preselected each time. */}
            <WeekTimes
              key={`${data.week}|${data.doctor}`}
              data={data}
              showDoctor={allDoctors}
              onSelect={onSelect}
              onShowWeek={(week) => go({ week })}
            />
          </Box>
        </Flex>
      </Card>
    </Flex>
  );
}

function NextAvailable({
  time,
  today,
  showDoctor,
  onSelect,
}: {
  time: AvailableTime;
  today: string;
  showDoctor: boolean;
  onSelect: () => void;
}) {
  return (
    <Card size="2" className="availability__next">
      <Flex
        direction={{ initial: 'column', xs: 'row' }}
        justify="between"
        align={{ initial: 'start', xs: 'center' }}
        gap="3"
      >
        <Flex gap="3" align="center">
          <span className="availability__next-icon">
            <ClockIcon size={20} />
          </span>
          <Flex direction="column">
            <Text size="2" color="gray">
              Nächster freier Termin
            </Text>
            <Text size="3" weight="bold">
              {formatDateTime(time.startsAt, today)}
            </Text>
            {showDoctor && <Text size="2">{time.doctor.displayName}</Text>}
          </Flex>
        </Flex>
        <Button size="3" onClick={onSelect}>
          Diesen Termin wählen
          <ArrowRightIcon />
        </Button>
      </Flex>
    </Card>
  );
}

type WeekTimesProps = {
  data: BrowserData;
  showDoctor: boolean;
  onSelect: (option: TimeOption) => void;
  onShowWeek: (week: string) => void;
};

function WeekTimes({ data, showDoctor, onSelect, onShowWeek }: WeekTimesProps) {
  const byDay = useMemo(() => groupByDay(data.times), [data.times]);
  const days = useMemo(
    () => Array.from({ length: 7 }, (_, index) => addDays(data.week, index)),
    [data.week],
  );
  const [selected, setSelected] = useState(
    () => days.find((day) => byDay.has(day)) ?? days[0] ?? data.week,
  );
  const dayLabelId = useId();

  if (data.error) return null;

  if (byDay.size === 0) {
    const nextWeek = data.next ? mondayOf(dateKey(new Date(data.next.startsAt))) : undefined;
    return (
      <Flex direction="column" align="center" gap="3" py="6" className="availability__empty">
        <CalendarEmptyIcon size={32} />
        <Text as="p" size="3" weight="medium" align="center">
          In dieser Woche ist leider kein Termin frei.
        </Text>
        {nextWeek && nextWeek !== data.week ? (
          <Button variant="soft" size="3" onClick={() => onShowWeek(nextWeek)}>
            Zur Woche mit dem nächsten freien Termin
          </Button>
        ) : (
          data.week < data.lastWeek && (
            <Button variant="soft" size="3" onClick={() => onShowWeek(addDays(data.week, 7))}>
              Nächste Woche ansehen
            </Button>
          )
        )}
      </Flex>
    );
  }

  const options = byDay.get(selected) ?? [];
  const parts = (['morning', 'afternoon', 'evening'] as DayPart[])
    .map((part) => ({ part, options: options.filter((o) => dayPart(o.startsAt) === part) }))
    .filter((group) => group.options.length > 0);

  return (
    <Flex direction="column" gap="5">
      <Text id={dayLabelId} className="sr-only">
        Tag wählen
      </Text>
      <RadioCards.Root
        value={selected}
        onValueChange={setSelected}
        aria-labelledby={dayLabelId}
        className="availability__days"
        size="1"
        gap="2"
      >
        {days.map((day) => {
          const count = byDay.get(day)?.length ?? 0;
          const isToday = day === data.today;
          return (
            <RadioCards.Item
              key={day}
              value={day}
              disabled={count === 0}
              aria-label={`${formatDay(day, data.today)}${isToday ? ' (heute)' : ''}: ${
                count === 0
                  ? 'kein Termin frei'
                  : `${count} ${count === 1 ? 'Uhrzeit' : 'Uhrzeiten'} frei`
              }`}
              className="availability__day"
            >
              <Flex direction="column" align="center" gap="1">
                <Text size="1" color="gray">
                  {isToday ? 'Heute' : formatWeekdayShort(day)}
                </Text>
                <Text size="5" weight="bold">
                  {formatDayOfMonth(day)}
                </Text>
                {count > 0 ? (
                  <Badge size="1" variant="soft" radius="full" highContrast>
                    {count} frei
                  </Badge>
                ) : (
                  <Text size="1" color="gray">
                    –
                  </Text>
                )}
              </Flex>
            </RadioCards.Item>
          );
        })}
      </RadioCards.Root>

      <Flex direction="column" gap="4">
        <Heading as="h3" size="3">
          {formatDay(selected, data.today)}
        </Heading>
        {parts.length === 0 ? (
          <Text as="p" size="2" color="gray">
            An diesem Tag ist kein Termin frei. Bitte wählen Sie einen anderen Tag.
          </Text>
        ) : (
          parts.map(({ part, options: partOptions }) => (
            <section key={part} aria-label={DAY_PART_LABELS[part]}>
              <Text as="p" size="2" color="gray" weight="medium" mb="2">
                {DAY_PART_LABELS[part]}
              </Text>
              <div className="availability__times">
                {partOptions.map((option) => (
                  <TimeButton
                    key={option.startsAt}
                    option={option}
                    showDoctor={showDoctor}
                    onSelect={onSelect}
                  />
                ))}
              </div>
            </section>
          ))
        )}
      </Flex>
    </Flex>
  );
}

function TimeButton({
  option,
  showDoctor,
  onSelect,
}: {
  option: TimeOption;
  showDoctor: boolean;
  onSelect: (option: TimeOption) => void;
}) {
  const time = formatTime(option.startsAt);
  const [first] = option.doctors;
  const caption = !showDoctor
    ? undefined
    : option.doctors.length > 1
      ? `${option.doctors.length} zur Auswahl`
      : first?.displayName;
  const label =
    option.doctors.length > 1
      ? `${time} Uhr, ${option.doctors.length} Ärztinnen oder Ärzte zur Auswahl`
      : `${time} Uhr${showDoctor && first ? `, ${first.displayName}` : ''}`;

  return (
    <Button
      variant="surface"
      size="3"
      className="availability__time"
      aria-label={label}
      onClick={() => onSelect(option)}
    >
      <Flex direction="column" align="center" width="100%" minWidth="0">
        <span>{time}</span>
        {caption && (
          <Text size="1" color="gray" weight="regular" truncate className="availability__caption">
            {caption}
          </Text>
        )}
      </Flex>
    </Button>
  );
}
