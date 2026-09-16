# Room Daylight

Room Daylight estimates the natural daylight available inside individual rooms and exposes the result as a Home Assistant illuminance sensor.

It combines an outdoor lux reading with sun position, room floor area, window size and window orientation. Optional blinds or curtains can exclude covered windows, and optional indoor lux sensors can gently correct the estimate while artificial lights are off.

Room Daylight does not calculate cloud or weather effects itself. The selected outdoor illuminance sensor should already represent current outdoor brightness.

If you do not have a physical outdoor lux sensor, [Illuminance](https://github.com/pnbruckner/ha-illuminance) is a useful companion integration.

Configuration is handled entirely through the Home Assistant UI, and each room can be reconfigured later.
