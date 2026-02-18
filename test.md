### For /run_c
>
{
	"code": "#include <stdio.h>\n\nint main(void)\n{\n    printf(\"Muhahaha Test HELOO WORLD\\n\");\n    return (0);\n}",
	"stdin": ""
}

>
{
	"code": "#include <stdio.h>\n\nint main(void)\n{\n    char name[100];\n\n    if (fgets(name, sizeof(name), stdin) == NULL)\n        return (1);\n\n    printf(\"Hello, %s\", name);\n\n    return (0);\n}",
	"stdin": "Test\n"
}
