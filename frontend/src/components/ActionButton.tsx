import Button, {type ButtonProps} from "@mui/material/Button";

export function ActionButton({className = "", ...props}: ButtonProps) {
    const isPrimary = className.includes("action-button-primary");
    const isStrong = className.includes("action-button-strong");

    return (
        <Button
            className={className}
            color={isStrong ? "secondary" : "primary"}
            disableElevation
            variant={isPrimary || isStrong ? "contained" : "outlined"}
            {...props}
        />
    );
}
