import Button, {type ButtonProps} from "react-bootstrap/Button";

export function ActionButton({className = "", ...props}: ButtonProps) {
    const isPrimary = className.includes("action-button-primary");
    const isStrong = className.includes("action-button-strong");

    return (
        <Button
            className={className}
            size="sm"
            variant={
                isStrong
                    ? "warning"
                    : isPrimary
                        ? "primary"
                        : "outline-secondary"
            }
            {...props}
        />
    );
}
