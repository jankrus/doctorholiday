import { Badge, Card, Flex, Text } from '@radix-ui/themes';
import type { ReactNode } from 'react';
import type { Appointment } from '../../appointments/api';
import { needsFasting, reasonLabel } from '../../appointments/reasons';
import {
  dateKey,
  formatDay,
  formatDayOfMonth,
  formatMonthShort,
  formatTimeRange,
  formatWeekdayShort,
} from '../../appointments/time';
import { StethoscopeIcon } from '../icons';
import './AppointmentCard.css';

type Props = {
  appointment: Appointment;
  today: string;
  /** Badge above the date, e.g. „Nächster Termin“. */
  highlight?: string;
  /** Relative day („morgen“, „in 6 Tagen“), shown as a badge at the top right. */
  when?: string;
  /** Stronger look for the next appointment. */
  featured?: boolean;
  /** Muted look for past and cancelled appointments. */
  muted?: boolean;
  /** Status line, e.g. the change deadline. */
  footer?: ReactNode;
  /** Buttons at the end of the card. */
  actions?: ReactNode;
};

/** One appointment: date tile, day and time, doctor, reason and status. */
export function AppointmentCard({
  appointment,
  today,
  highlight,
  when,
  featured,
  muted,
  footer,
  actions,
}: Props) {
  const day = dateKey(new Date(appointment.startsAt));
  const cancelled = appointment.status === 'CANCELLED';
  const className = [
    'appointment-card',
    featured && 'appointment-card--featured',
    muted && 'appointment-card--muted',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <Card size={featured ? '3' : '2'} className={className}>
      <Flex direction="column" gap="4">
        <Flex gap="4" align="start">
          <div className="appointment-card__tile" aria-hidden="true">
            <span className="appointment-card__month">{formatMonthShort(day)}</span>
            <span className="appointment-card__day">{formatDayOfMonth(day)}</span>
            <span className="appointment-card__weekday">{formatWeekdayShort(day)}</span>
          </div>
          <Flex direction="column" gap="1" minWidth="0" flexGrow="1">
            {highlight && (
              <Text size="1" weight="bold" className="appointment-card__highlight">
                {highlight}
              </Text>
            )}
            <Text
              as="p"
              size="4"
              weight="bold"
              className={cancelled ? 'appointment-card__struck' : undefined}
            >
              {formatDay(day, today)}
            </Text>
            <Text as="p" size="3" color="gray">
              {formatTimeRange(appointment.startsAt, appointment.endsAt)}
            </Text>
            <Text as="p" size="2" className="appointment-card__doctor">
              <StethoscopeIcon />
              {appointment.doctor.displayName}
            </Text>
            <Flex gap="2" wrap="wrap" mt="2">
              <Badge color="gray" variant="soft" size="2" highContrast>
                {reasonLabel(appointment.reason)}
              </Badge>
              {cancelled && (
                <Badge color="gray" variant="outline" size="2">
                  {appointment.cancelledBy === 'PRACTICE' ? 'Von der Praxis abgesagt' : 'Abgesagt'}
                </Badge>
              )}
              {!cancelled && needsFasting(appointment.reason) && !muted && (
                <Badge color="amber" variant="soft" size="2" highContrast>
                  Nüchtern erscheinen
                </Badge>
              )}
              {!cancelled && appointment.bookedBy === 'PRACTICE' && !muted && (
                <Badge color="gray" variant="outline" size="2">
                  Von der Praxis gebucht
                </Badge>
              )}
            </Flex>
          </Flex>
          {when && (
            <Badge
              size="2"
              variant={featured ? 'solid' : 'soft'}
              color={featured ? undefined : 'gray'}
              className="appointment-card__when"
            >
              {when.charAt(0).toUpperCase() + when.slice(1)}
            </Badge>
          )}
        </Flex>
        {(footer || actions) && (
          <Flex
            direction={{ initial: 'column', sm: 'row' }}
            justify="between"
            align={{ initial: 'stretch', sm: 'center' }}
            gap="3"
            className="appointment-card__footer"
          >
            <div>{footer}</div>
            {actions && (
              <Flex gap="2" justify="end" flexShrink="0">
                {actions}
              </Flex>
            )}
          </Flex>
        )}
      </Flex>
    </Card>
  );
}
