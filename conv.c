#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <stdio.h>
#include <stdint.h>

static PyObject *img_to_7c(PyObject *self, PyObject *args)
{
    int w, h, planes;
    PyObject *pltdata, *imgdata;
    if (!PyArg_ParseTuple(args, "iiOiO", &w, &h, &pltdata, &planes, &imgdata))
        return NULL;

    // Decode palette
    uint32_t palette[7] = {};
    if (PyList_Size(pltdata) != 7)
        return NULL;
    for (int i = 0; i < 7; i++) {
        const uint8_t *p = (uint8_t *)PyByteArray_AsString(PyList_GET_ITEM(pltdata, i));
        palette[i] = (p[0] << 16) | (p[1] << 8) | (p[2] << 0);
    }

    // Process image data
    PyObject *data = PyByteArray_FromStringAndSize(NULL, 0);
    PyByteArray_Resize(data, h * w / 2);
    uint8_t *pdata = (uint8_t *)PyByteArray_AsString(data);
    if (PyList_Size(imgdata) != h)
        return NULL;
    for (int y = 0; y < h; y++) {
        const uint8_t *p = (uint8_t *)PyByteArray_AsString(PyList_GET_ITEM(imgdata, y));
        uint8_t v;
        for (int x = 0; x < w; x++) {
            uint32_t r = p[x * 4 + 0];
            uint32_t g = p[x * 4 + 1];
            uint32_t b = p[x * 4 + 2];
			uint32_t c = (r << 16) | (g << 8) | b;

			int p = -1;
			for (int i = 0; i < 7; i++)
				if (c == palette[i])
					p = i;
			if (p < 0) {
				fprintf(stderr, "Unknown colour: x=%d y=%d c=0x%06x\n", x, y, c);
                return NULL;
			}
			v |= p;

			if ((x % 2) == 1)
                pdata[(y * w + x) / 2] = v;
			v <<= 4;
        }
    }
    return data;
}

static PyMethodDef module_methods[] = {
    {"img_to_7c", img_to_7c, METH_VARARGS, NULL},
    {NULL, NULL, 0, NULL}   // Sentinel
};

static struct PyModuleDef conv_module = {
    PyModuleDef_HEAD_INIT,
    "conv", // Name
    NULL,   // docstring
    -1,
    module_methods,
};

PyMODINIT_FUNC PyInit_conv(void)
{
    return PyModule_Create(&conv_module);
}
