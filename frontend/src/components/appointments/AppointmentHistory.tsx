import { Badge, Button, Flex, Text } from '@radix-ui/themes';
import { useState } from 'react';
import type { Appointment } from '../../appointments/api';
import { reasonLabel } from '../../appointments/reasons';
import { dateKey, formatDay, formatTimeRange } from '../../appointments/time';
import './AppointmentHistory.css';

/** Entries shown before „Alle anzeigen“. */
const COLLAPSED = 4;

type Props = {
  /** Past appointments and cancelled future ones, newest first. */
  appointments: Appointment[];
  today: string;
};

/** Compact timeline of past and cancelled appointments: day, time, doctor, reason and status. */
export function AppointmentHistory({ appointments, today }: Props) {
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? appointments : appointments.slice(0, COLLAPSED);

  return (
    <Flex direction="column" gap="3">
      <ul className="history">
        {shown.map((appointment) => {
          const day = dateKey(new Date(appointment.startsAt));
          const cancelled = appointment.status === 'CANCELLED';
          return (
            <li
              key={appointment.id}
              className={cancelled ? 'history__item history__item--cancelled' : 'history__item'}
            >
              <Text
                as="p"
                size="2"
                weight="bold"
                className={cancelled ? 'history__struck' : undefined}
              >
                {formatDay(day, today)}
              </Text>
              <Text as="p" size="2" color="gray">
                {formatTimeRange(appointment.startsAt, appointment.endsAt)} ·{' '}
                {appointment.doctor.displayName}
              </Text>
              <Flex gap="2" wrap="wrap" mt="1">
                <Badge color="gray" variant="soft" size="1" highContrast>
                  {reasonLabel(appointment.reason)}
                </Badge>
                {cancelled && (
                  <Badge color="gray" variant="outline" size="1">
                    {appointment.cancelledBy === 'PRACTICE'
                      ? 'Von der Praxis abgesagt'
                      : 'Abgesagt'}
                  </Badge>
                )}
              </Flex>
            </li>
          );
        })}
      </ul>
      {appointments.length > COLLAPSED && (
        <Button
          variant="ghost"
          color="gray"
          size="2"
          className="history__toggle"
          aria-expanded={expanded}
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? 'Weniger anzeigen' : `Alle ${appointments.length} anzeigen`}
        </Button>
      )}
    </Flex>
  );
}
