import Stack from "@mui/material/Stack";

interface MetricRowsProps {
    rows: Array<[string, string | number]>;
}

export function MetricRows({rows}: MetricRowsProps) {
    return (
        <Stack className="stat-grid" spacing={0}>
            {rows.map(([label, value]) => (
                <div className="stat-row" key={label}>
                    <span>{label}</span>
                    <span>{value}</span>
                </div>
            ))}
        </Stack>
    );
}
