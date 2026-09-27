# NOAA MarineCadastre AIS Data Quality Report

- Raw rows: 5929631
- Processed rows: 5928519
- Unique vessels: 16294
- Timestamp range (UTC): ['2025-01-08T00:00:00Z', '2025-01-08T23:59:59Z']
- Geographic range: {'latitude': [np.float64(2.30697), np.float64(85.28678)], 'longitude': [np.float64(-175.14678), np.float64(146.49848)]}
- Missing coordinate rows: 0
- Invalid coordinate rows: 0
- Duplicate observations removed: 1112
- Processing time (seconds): 1479.63
- Processed file size (bytes): 305968306

## Source columns

mmsi, base_date_time, longitude, latitude, sog, cog, heading, vessel_name, imo, call_sign, vessel_type, status, length, width, draft, cargo, transceiver

## Missing values

```json
{
  "mmsi": 0,
  "base_date_time": 0,
  "longitude": 0,
  "latitude": 0,
  "sog": 12540,
  "cog": 1069760,
  "heading": 3000096,
  "vessel_name": 17112,
  "imo": 3563659,
  "call_sign": 724581,
  "vessel_type": 42576,
  "status": 2099726,
  "length": 131085,
  "width": 208548,
  "draft": 2626457,
  "cargo": 1962523,
  "transceiver": 0
}
```

## Provenance

The raw compressed source was preserved unchanged. AIS rows were streamed in bounded chunks; no synthetic values were introduced.
