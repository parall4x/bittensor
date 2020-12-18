#!/bin/python3


# def process(self):
#     return int.from_bytes(self.get_next_bytes(4), byteorder='little')
#
#
# def process_encode(self, value):
#     if 0 <= int(value) <= 2 ** 32 - 1:
#         return ScaleBytes(bytearray(int(value).to_bytes(4, 'little')))
#     else:
#         raise ValueError('{} out of range for u32'.format(value))
#
#

import math

value = 1.8888477744995


def encode(value):
    remainder, integer = math.modf(value)

    if integer >= 2 or integer < 0:
        raise ValueError('{} out of range for u1f31')


    print(remainder, integer)





def conv_to_int(val):
    return int(float(val) * int(4294967295)) >> 1


def conv_to_float(val):
    return val / 4294967295

integer = conv_to_int(0.5)

print(integer)
