import {createTheme} from "@mui/material/styles";

export const plannerTheme = createTheme({
    palette: {
        mode: "light",
        primary: {main: "#0d7a5f", dark: "#064c3d"},
        secondary: {main: "#1f5f87"},
        background: {default: "#f3efe6", paper: "#fffaf2"},
        error: {main: "#ad3131"},
    },
    shape: {borderRadius: 14},
    typography: {
        fontFamily: '"Avenir Next", "IBM Plex Sans", "Segoe UI", sans-serif',
        button: {fontWeight: 700, textTransform: "none"},
    },
});
