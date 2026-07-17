interface MetricRowsProps {
    rows: Array<[string, string | number]>;
}

export function MetricRows({rows}: MetricRowsProps) {
    return (
        <div className="stat-grid">
            {rows.map(([label, value]) => (
                <div className="stat-row" key={label}>
                    <span>{label}</span>
                    <span>{value}</span>
                </div>
            ))}
        </div>
    );
}
