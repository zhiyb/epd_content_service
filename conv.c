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
    // Black, white, green, blue, red, yellow, orange, (clear)
    static const uint32_t n_colours = 7;
    uint32_t palette[8] = {};
    if (PyList_Size(pltdata) != n_colours)
        return NULL;
    for (int i = 0; i < n_colours; i++) {
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
			for (int i = 0; i < n_colours; i++)
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

static PyObject *img_to_rwb(PyObject *self, PyObject *args)
{
    int w, h, planes;
    PyObject *pltdata, *imgdata;
    if (!PyArg_ParseTuple(args, "iiOiO", &w, &h, &pltdata, &planes, &imgdata))
        return NULL;

    // Decode palette
    // Black, white, red
    static const uint32_t n_colours = 3;
    uint32_t palette[8] = {};
    if (PyList_Size(pltdata) != n_colours)
        return NULL;
    for (int i = 0; i < n_colours; i++) {
        const uint8_t *p = (uint8_t *)PyByteArray_AsString(PyList_GET_ITEM(pltdata, i));
        palette[i] = (p[0] << 16) | (p[1] << 8) | (p[2] << 0);
    }

    // Process image data
    if (PyList_Size(imgdata) != h)
        return NULL;

    // Black-White-Red, separated to BW and Red blocks
    PyObject *bw = PyByteArray_FromStringAndSize(NULL, 0);
    PyObject *red = PyByteArray_FromStringAndSize(NULL, 0);
    PyByteArray_Resize(bw, h * w / 8);
    PyByteArray_Resize(red, h * w / 8);
    uint8_t *p_bw = (uint8_t *)PyByteArray_AsString(bw);
    uint8_t *p_red = (uint8_t *)PyByteArray_AsString(red);

	for (int y = 0; y < h; y++) {
        const uint8_t *p = (uint8_t *)PyByteArray_AsString(PyList_GET_ITEM(imgdata, y));
		uint8_t v_bw = 0, v_red = 0;
		for (int x = 0; x < w; x++) {
            uint32_t r = p[x * 4 + 0];
            uint32_t g = p[x * 4 + 1];
            uint32_t b = p[x * 4 + 2];
			uint32_t c = (r << 16) | (g << 8) | b;

			int p = -1;
			for (int i = 0; i < n_colours; i++)
				if (c == palette[i])
					p = i;

            switch (p) {
            case 0:     // Black
                break;
            case 1:     // White
                v_bw |= 1;
                break;
            case 2:     // Red
                v_red |= 1;
                break;
            default:
				fprintf(stderr, "Unknown colour: x=%d y=%d c=0x%06x\n", x, y, c);
                return NULL;
            }

			if (x % 8 == 7) {
                p_bw[(y * w + x) / 8] = v_bw;
                p_red[(y * w + x) / 8] = v_red;
            }
			v_bw <<= 1;
			v_red <<= 1;
		}
	}

    return PyByteArray_Concat(bw, red);
}

static PyObject *img_to_rwb4(PyObject *self, PyObject *args)
{
    int w, h, planes;
    PyObject *pltdata, *imgdata;
    if (!PyArg_ParseTuple(args, "iiOiO", &w, &h, &pltdata, &planes, &imgdata))
        return NULL;

    // Decode palette
    // Black, white, red
    static const uint32_t n_colours = 3;
    uint32_t palette[8] = {};
    if (PyList_Size(pltdata) != n_colours)
        return NULL;
    for (int i = 0; i < n_colours; i++) {
        const uint8_t *p = (uint8_t *)PyByteArray_AsString(PyList_GET_ITEM(pltdata, i));
        palette[i] = (p[0] << 16) | (p[1] << 8) | (p[2] << 0);
    }

    // Process image data
    if (PyList_Size(imgdata) != h)
        return NULL;

    // Black-White-Red, aligned to 4-bit data format
    PyObject *data = PyByteArray_FromStringAndSize(NULL, 0);
    PyByteArray_Resize(data, h * w / 2);
    uint8_t *p_data = (uint8_t *)PyByteArray_AsString(data);

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
			for (int i = 0; i < n_colours; i++)
				if (c == palette[i])
					p = i;
			if (p < 0) {
				fprintf(stderr, "Unknown colour: x=%d y=%d c=0x%06x\n", x, y, c);
                return NULL;
			}

            switch (p) {
            case 0:     // Black
                break;
            case 1:     // White
                v |= 0b0011;
                break;
            case 2:     // Red
                v |= 0b0100;
                break;
            default:
				fprintf(stderr, "Unknown colour: x=%d y=%d c=0x%06x\n", x, y, c);
                return NULL;
            }

			if ((x % 2) == 1)
                p_data[(y * w + x) / 2] = v;
			v <<= 4;
        }
    }

    return data;
}


static PyMethodDef module_methods[] = {
    {"img_to_7c", img_to_7c, METH_VARARGS, NULL},
    {"img_to_rwb", img_to_rwb, METH_VARARGS, NULL},
    {"img_to_rwb4", img_to_rwb4, METH_VARARGS, NULL},
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
